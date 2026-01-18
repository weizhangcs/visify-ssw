import json
import logging
from collections import defaultdict
from typing import Any, Dict, List

from apps.common.schemas.annotation.workbench import DataOrigin

# 引用 AnnotationService 用于加载 Job 数据
from .annotation_service import AnnotationService

logger = logging.getLogger(__name__)


class ArtifactAuditService:
    """
    针对 V5.1 Schema 的产出物审计服务。

    [核心升级 - 2025-12-09]
    逻辑已完全对齐原 metrics_service.py：
    1. 引入“数据适配器”，将平铺的 V5.1 轨道数据重组为 Scene-Dialogue 嵌套结构。
    2. 复用“共现矩阵 (Co-occurrence)”计算逻辑。
    3. 复用“多维归一化 + 权重 (Presence 0.7 / Interaction 0.3)” 评分算法。
    """

    @classmethod
    def run_project_audit(cls, project) -> dict:
        """
        [业务编排] 执行项目审计
        流程：生成数据集 -> 审计 -> 更新状态 -> 保存报告
        """
        try:
            # 1. 强制刷新 Narrative Dataset (Blueprint)
            # 确保发给 Cloud/Inference 的是最新数据
            AnnotationService.generate_narrative_dataset(project)

            # 2. 执行审计
            # AuditService 会重新读取 Jobs，这和 generate_narrative_dataset 读的是同一份数据源
            report_data = cls.audit_project(project)

            # 3. 持久化审计报告 (AUDIT)
            json_output = json.dumps(report_data, indent=2, ensure_ascii=False)
            project.save_artifact("AUDIT", json_output)

            # 4. 更新项目状态为 COMPLETED
            if project.status != "COMPLETED":
                project.status = "COMPLETED"
                project.save(update_fields=["status"])

                # [状态联动] 自动完成所有 Job
                for job in project.jobs.all():
                    if job.status != "COMPLETED":
                        try:
                            job.complete_annotation()
                            # [New] 触发数据发布 (Publish Artifacts for RAG)
                            # 确保 Job 包含最新的结构化数据供下游使用
                            AnnotationService.publish_job_artifacts(job)
                            job.save()
                        except Exception as e:
                            logger.warning(f"Auto-complete job {job.id} failed: {e}")

            return report_data

        except Exception as e:
            logger.error(f"Run Project Audit failed for Project {project.id}: {e}", exc_info=True)
            raise e

    @classmethod
    def audit_project(cls, project) -> Dict[str, Any]:
        """
        主入口：对 AnnotationProject 实例进行全量审计
        """
        audit_report = {
            "project_info": {
                "id": str(project.id),
                "name": project.name,
                "total_jobs": 0,
                "valid_jobs": 0,
            },
            "technical_audit": {"status": "pass", "errors": []},
            "engineering_stats": {
                "total_duration": 0.0,
                "track_counts": defaultdict(int),
                "ai_vs_human": {"ai_modified": 0, "human_modified": 0},
            },
            "semantic_audit": {},
        }

        valid_jobs = project._get_valid_jobs()
        audit_report["project_info"]["total_jobs"] = project.jobs.count()
        audit_report["project_info"]["valid_jobs"] = valid_jobs.count()

        # --- 临时数据池：用于后续的“适配器”重组 ---
        all_scenes_pool = []
        all_dialogues_pool = []

        # 遍历 Jobs 进行聚合
        for job in valid_jobs:
            try:
                # [1. 技术审计] 加载 Schema
                media_anno = AnnotationService.load_annotation(job)

                # [2. 工程统计]
                current_duration = media_anno.duration
                audit_report["engineering_stats"]["total_duration"] += current_duration

                # [3. 数据分流 & 统计]
                # 直接遍历 Pydantic 对象以访问 Context 信息

                def process_track_stats(track_name, items):
                    """更新计数并统计 AI/Human 来源"""
                    count = len(items)
                    audit_report["engineering_stats"]["track_counts"][track_name] += count

                    for item in items:
                        if item.context.origin == DataOrigin.HUMAN:
                            audit_report["engineering_stats"]["ai_vs_human"]["human_modified"] += 1
                        else:
                            audit_report["engineering_stats"]["ai_vs_human"]["ai_modified"] += 1

                # A. Scenes
                process_track_stats("scenes", media_anno.scenes)
                for s in media_anno.scenes:
                    # 扁平化为 Dict 供语义算法使用
                    flat_s = {
                        "start": s.start,
                        "end": s.end,
                        **s.content.model_dump(),
                        "_unique_id": f"{job.id}_{s.context.id}",
                    }
                    all_scenes_pool.append(flat_s)

                # B. Dialogues
                process_track_stats("dialogues", media_anno.dialogues)
                for d in media_anno.dialogues:
                    flat_d = {"start": d.start, "end": d.end, **d.content.model_dump()}
                    all_dialogues_pool.append(flat_d)

                # C. Others (仅统计)
                process_track_stats("captions", media_anno.captions)
                process_track_stats("highlights", media_anno.highlights)

            except Exception as e:
                error_msg = f"Job {job.id} 加载失败: {str(e)}"
                audit_report["technical_audit"]["errors"].append(error_msg)
                logger.error(error_msg)

        if audit_report["technical_audit"]["errors"]:
            audit_report["technical_audit"]["status"] = "failed"

        # --- [4. 语义审计核心] ---
        # 步骤 A: 数据适配 (Adapter) - 将对白按时间戳塞回场景
        mapped_scenes = cls._map_dialogues_to_scenes(all_scenes_pool, all_dialogues_pool)

        # 步骤 B: 算法执行 - 调用移植过来的 metrics_service 逻辑
        char_analysis = cls._calculate_advanced_metrics(mapped_scenes)
        audit_report["semantic_audit"] = char_analysis

        return audit_report

    @staticmethod
    def _map_dialogues_to_scenes(scenes: List[Dict], dialogues: List[Dict]) -> Dict[str, Dict]:
        """
        [数据适配器]
        将平铺的 dialogues 列表，根据 start_time 归位到对应的 scenes 中。
        这是计算“共现 (Co-occurrence)”的前提。
        """
        # 结果格式: { unique_scene_id: { ..., "dialogues": [] } }
        scene_map = {}

        # 按时间排序优化匹配效率
        sorted_scenes = sorted(scenes, key=lambda x: x.get("start", 0))

        # 初始化 map
        for s in sorted_scenes:
            s_copy = s.copy()
            s_copy["dialogues"] = []
            scene_map[s["_unique_id"]] = s_copy

        # 分发对白
        # 逻辑：对白的开始时间只要落在场景区间内，就算该场景的对白
        for d in dialogues:
            d_start = d.get("start", 0)
            # 加上微小偏移量 0.1s，防止刚好压线的问题
            d_check = d_start + 0.01

            for s in sorted_scenes:
                if s.get("start", 0) <= d_check < s.get("end", 0):
                    scene_map[s["_unique_id"]]["dialogues"].append(d)
                    break

        return scene_map

    @classmethod
    def _calculate_advanced_metrics(cls, scenes_map: Dict) -> Dict:
        """
        [算法移植]
        完全复刻 CharacterMetricsCalculator 的逻辑。
        """
        # --- 步骤 1: 本地预处理 (移植自 metrics_service._local_preprocessing) ---
        metrics = defaultdict(
            lambda: {
                "scene_count": 0,
                "dialogue_count": 0,
                "dialogue_total_length": 0,
                "dialogue_total_duration": 0.0,
                "co_occurrence": defaultdict(int),
                "raw_names": set(),  # 记录原始拼写
            }
        )

        # 排除模式 (这里可以做成配置项)
        exclude_patterns = ["Minor", "路人", "Unknown"]

        for scene_obj in scenes_map.values():
            dialogues_in_scene = scene_obj.get("dialogues", [])

            # 1.1 识别当前场景出现的角色 (Set 去重)
            present_characters = set()

            # 先遍历一遍找出本场所有角色
            for d in dialogues_in_scene:
                raw_speaker = d.get("speaker", "").strip()
                if not raw_speaker:
                    continue

                # 排除过滤
                if any(raw_speaker.startswith(p) for p in exclude_patterns):
                    continue

                # 归一化 Key (用于聚合统计，忽略大小写)
                speaker_key = " ".join(raw_speaker.lower().split())

                present_characters.add(speaker_key)
                metrics[speaker_key]["raw_names"].add(raw_speaker)

            # 1.2 更新场景计数 (Scene Count)
            for char_key in present_characters:
                metrics[char_key]["scene_count"] += 1

            # 1.3 计算共现 (Interaction / Co-occurrence)
            # 如果本场只有1个人，就没有共现
            for char1 in present_characters:
                for char2 in present_characters:
                    if char1 != char2:
                        metrics[char1]["co_occurrence"][char2] += 1

            # 1.4 累加对白指标 (Lines, Words, Duration)
            for d in dialogues_in_scene:
                raw_speaker = d.get("speaker", "").strip()
                if not raw_speaker:
                    continue

                # 同样要做排除检查
                if any(raw_speaker.startswith(p) for p in exclude_patterns):
                    continue

                speaker_key = " ".join(raw_speaker.lower().split())

                # 只有在 present_characters 里的才算 (防止逻辑不一致)
                if speaker_key in present_characters:
                    metrics[speaker_key]["dialogue_count"] += 1
                    metrics[speaker_key]["dialogue_total_length"] += len(d.get("text", ""))  # V5 Schema 是 text

                    # V5 Schema 直接是 float 时间
                    dur = d.get("end", 0) - d.get("start", 0)
                    metrics[speaker_key]["dialogue_total_duration"] += dur

        # --- 步骤 2: 计算重要度 (移植自 metrics_service._calculate_importance_scores) ---
        roster = []
        if not metrics:
            return {"character_roster": [], "name_issues": []}

        # 2.1 获取最大值用于归一化 (防止除以0)
        target_chars = metrics.keys()

        def safe_max(iterable):
            val = max(iterable, default=0)
            return val if val > 0 else 1

        max_vals = {
            "scene": safe_max(metrics[c]["scene_count"] for c in target_chars),
            "dialogue": safe_max(metrics[c]["dialogue_count"] for c in target_chars),
            "length": safe_max(metrics[c]["dialogue_total_length"] for c in target_chars),
            "duration": safe_max(metrics[c]["dialogue_total_duration"] for c in target_chars),
            "interaction": safe_max(len(metrics[c]["co_occurrence"]) for c in target_chars),
        }

        # 权重配置 (保持原默认值)
        weights = {"presence": 0.7, "interaction": 0.3}

        for key, data in metrics.items():
            # 复刻原版公式：四维归一化求和
            presence_score = (
                data["scene_count"] / max_vals["scene"]
                + data["dialogue_count"] / max_vals["dialogue"]
                + data["dialogue_total_length"] / max_vals["length"]
                + data["dialogue_total_duration"] / max_vals["duration"]
            )

            interaction_score = len(data["co_occurrence"]) / max_vals["interaction"]

            # 最终得分
            final_score = (presence_score * weights["presence"]) + (interaction_score * weights["interaction"])

            # 选一个最好看的名字用于展示 (取第一个原始写法)
            display_name = list(data["raw_names"])[0] if data["raw_names"] else key

            roster.append(
                {
                    "name": display_name,
                    "key": key,
                    "weight_score": round(final_score, 4),  # 综合得分
                    # 为了 Admin 进度条展示，这里做一个相对百分比 (最大可能得分约为 4 * 0.7 + 1 * 0.3 = 3.1)
                    # 简单处理：除以列表里最高的分数作为 100%
                    "_raw_score": final_score,
                    "stats": {
                        "lines": data["dialogue_count"],
                        "duration_sec": round(data["dialogue_total_duration"], 2),
                        "scene_count": data["scene_count"],  # 新增展示
                        "interaction_count": len(data["co_occurrence"]),  # 新增展示
                    },
                    "variations": list(data["raw_names"]),
                }
            )

        # 排序
        roster.sort(key=lambda x: x["weight_score"], reverse=True)

        # 补充 weight_percent (相对于第一名的百分比，用于 UI 进度条)
        top_score = roster[0]["_raw_score"] if roster else 1
        for r in roster:
            pct = (r["_raw_score"] / top_score) * 100 if top_score > 0 else 0
            r["weight_percent"] = f"{round(pct, 1)}%"
            del r["_raw_score"]  # 清理临时字段

        # --- 步骤 3: 检查拼写问题 ---
        issues = []
        for r in roster:
            if len(r["variations"]) > 1:
                issues.append({"level": "warning", "msg": f"角色 '{r['name']}' 存在多种拼写写法", "details": r["variations"]})

        return {"character_roster": roster, "name_issues": issues}
