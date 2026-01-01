# apps/atomflow/refinery/context.py

import logging
import time

from apps.common.atomflow.base_contexts import BaseAtomicContext, BasePipelineContext

from .models import Material, RefineryAtomPipeline
from .schemas import TechMeta, VisualSliceItem

logger = logging.getLogger(__name__)


class RefineryPipelineContext(BasePipelineContext):
    """
    [修正] 真实的执行上下文：
    通过 get_pipeline_instance 获取数据库中的轨迹记录。
    """

    def get_pipeline_instance(self):
        # [Fix] 预加载 rule 以优化查询，并注入缺失的 mode 属性
        pipeline = RefineryAtomPipeline.objects.select_related("rule").get(id=self.pipeline_id)
        if not hasattr(pipeline, "mode"):
            pipeline.mode = pipeline.rule.mode
        return pipeline


class RefineryAtomicContext(BaseAtomicContext):
    """
    旁路业务上下文：负责 Material 与 算子之间的数据平配。
    """

    def get_target_instance(self) -> Material:
        # 获取具体的业务模型实例
        # 预加载 pipeline 以减少查询
        return Material.objects.select_related("media", "media__asset", "pipeline", "pipeline__rule").get(
            id=self.target_id
        )

    @property
    def pipeline(self):
        """
        [新增] 获取关联的 Pipeline 实例
        基于 Material : Pipeline = 1 : 1 的严格关系
        """
        # 使用 OneToOneField 的反向关联名 'pipeline'
        # 如果不存在，会抛出 ObjectDoesNotExist，这里我们捕获并返回 None
        try:
            pipeline = self.target.pipeline
            if pipeline and not hasattr(pipeline, "mode"):
                pipeline.mode = pipeline.rule.mode
            return pipeline
        except RefineryAtomPipeline.DoesNotExist:
            return None

    def get_payload(self, op_slug: str):
        target = self.target
        # 使用动态分发模式：查找 _payload_{op_slug} 方法
        handler = getattr(self, f"_payload_{op_slug}", None)
        if handler:
            return handler(target)
        return {}

    def _payload_transcode(self, target):
        return {"source_video_path": target.media.source_video.path}

    def _payload_probe(self, target):
        # 修正：ProbeService.run 需要 proxy_path 和 temp_wav_path
        return {"proxy_path": target.proxy_video, "temp_wav_path": f"/tmp/atomflow_probe_{target.id}.wav"}  # 示例路径

    def _payload_hls(self, target):
        return {"proxy_video_path": target.proxy_video}

    def _payload_slicing(self, target):
        return {
            "proxy_video_path": target.proxy_video,
            "duration": target.duration,
            "dialogue_track": target.dialogue_track,
        }

    def _payload_frame_extract(self, target):
        return {"proxy_video_path": target.proxy_video, "slices": target.visual_slices}

    def _payload_text_analyze(self, target):
        # [修正] 数据源来自 material.media.source_subtitle (SRT文件相对路径)
        # 注意：source_subtitle 可能是 FileField (取.name) 或 CharField (直接取值)
        src_sub = getattr(target.media, "source_subtitle", None)
        rel_path = src_sub.name if hasattr(src_sub, "name") else src_sub
        return {"subtitle_path": str(rel_path)} if rel_path else {}

    def _payload_character_refine(self, target):
        # [修正] 语言代码转换 (e.g. zh_CN -> zh)
        asset = getattr(target.media, "asset", None)
        lang = "zh"
        if asset and asset.language:
            lang = asset.language.split("_")[0]

        return {
            "dialogue_track": target.dialogue_track,
            "video_title": target.media.title,
            "known_characters": asset.known_characters if asset else [],
            "lang": lang,
        }

    def _payload_sync(self, target):
        # [修正] 仅针对 visual_slices 中的关键帧进行同步
        asset_id = (
            str(target.media.asset.id) if hasattr(target.media, "asset") else "00000000-0000-0000-0000-000000000000"
        )
        return {"visual_slices": target.visual_slices, "asset_id": asset_id}

    def handle_result(self, op_slug: str, result: dict):
        """
        [核心职能] 结果回填逻辑统一收拢在此，剥离算子对数据库的感知。
        """
        target = self.target

        # 使用动态分发模式：查找 _handle_{op_slug} 方法
        handler = getattr(self, f"_handle_{op_slug}", None)
        if handler:
            handler(target, result)
        else:
            logger.warning(f"[Atomflow] 未找到 {op_slug} 的结果处理逻辑")
            return

        target.save()
        logger.info(f"[Atomflow] {op_slug} 结果已回填至 Material {target.id}")

        # [Fix] 同步更新 Pipeline Metrics (记分牌)
        # 只有记录了 Metrics，Scheduler 才能知道这一步完成了，从而派发下一步
        self._update_pipeline_metrics(op_slug)

    def _update_pipeline_metrics(self, op_slug: str):
        pipeline = self.pipeline
        if not pipeline:
            return

        # 从 Rule Config 中反查当前 op_slug 对应的 sequence
        # 假设 rules_config 是 List[Dict]，例如 [{"seq": 1, "unit_slug": "transcode", ...}]
        rule_config = pipeline.rule.rules_config
        step_info = next((s for s in rule_config if s["unit_slug"] == op_slug), None)

        if step_info:
            seq = str(step_info["seq"])
            metrics = pipeline.metrics or {}
            # 只有当 metrics 中没有记录，或者状态不是 SUCCESS 时才更新
            # 避免覆盖 Task 层面可能记录的更详细信息 (如 duration)
            if seq not in metrics or metrics[seq].get("status") != "SUCCESS":
                metrics[seq] = {"slug": op_slug, "status": "SUCCESS", "finished_at": time.time()}
                pipeline.metrics = metrics
                pipeline.save(update_fields=["metrics"])
                logger.info(f"[Atomflow] Pipeline {pipeline.id} metrics updated for step {seq} ({op_slug})")

    def _handle_transcode(self, target, result):
        target.proxy_video = result.get("rel_path")

    def _handle_probe(self, target, result):
        target.duration = result.get("duration", 0.0)
        # [Schema] 校验并清洗 tech_meta
        target.tech_meta = TechMeta(**result.get("tech_meta", {})).model_dump()
        target.waveform_data = result.get("waveform_data", [])

    def _handle_hls(self, target, result):
        target.hls_playlist = result.get("rel_path")

    def _handle_slicing(self, target, result):
        raw_slices = result.get("slices", [])
        target.visual_slices = [VisualSliceItem(**s).model_dump() for s in raw_slices]

    def _handle_frame_extract(self, target, result):
        raw_slices = result.get("slices", [])
        target.visual_slices = [VisualSliceItem(**s).model_dump() for s in raw_slices]

    def _handle_text_analyze(self, target, result):
        target.dialogue_track = result.get("dialogue_track", [])

    def _handle_character_refine(self, target, result):
        target.dialogue_track = result.get("dialogue_track", [])

    def _handle_sync(self, target, result):
        # [修正] 回填更新后的 visual_slices (包含云端 URL)
        if "slices" in result:
            raw_slices = result["slices"]
            target.visual_slices = [VisualSliceItem(**s).model_dump() for s in raw_slices]

    def check_is_ready(self, slug: str) -> bool:
        target = self.target
        if slug == "transcode":
            return bool(target.media.source_video)
        if slug == "probe":
            return bool(target.proxy_video)
        if slug == "hls":
            return bool(target.proxy_video)
        if slug == "text_analyze":
            return True
        if slug == "slicing":
            return bool(target.proxy_video) and bool(target.dialogue_track)
        if slug == "frame_extract":
            return bool(target.proxy_video) and bool(target.visual_slices)
        if slug == "character_refine":
            return bool(target.dialogue_track)
        if slug == "sync":
            # 同步依赖于切片和关键帧已生成
            return bool(target.visual_slices)
        return True

    def check_is_done(self, slug: str) -> bool:
        target = self.target

        # [混合策略]
        # 1. 对于产出物明确的物理算子，优先检查物理结果 (Double Check)
        if slug == "transcode":
            return bool(target.proxy_video)
        if slug == "probe":
            return target.duration > 0
        if slug == "hls":
            return bool(target.hls_playlist)
        if slug == "text_analyze":
            return bool(target.dialogue_track)
        if slug == "slicing":
            return bool(target.visual_slices)
        if slug == "frame_extract":
            if not target.visual_slices:
                return False
            return all(s.get("frames") for s in target.visual_slices)
        if slug == "sync":
            # 检查是否已完成同步：判断第一个切片的第一个帧是否为云端地址
            if not target.visual_slices:
                return False
            first_slice = target.visual_slices[0]
            frames = first_slice.get("frames", [])
            if not frames:
                return False
            return frames[0].get("path", "").startswith("http")

        # 2. 对于产出物混合或逻辑复杂的算子 (如 character_refine)，回退到检查 Pipeline Metrics
        if slug == "character_refine":
            pipeline = self.pipeline
            if not pipeline or not pipeline.metrics:
                return False

            # 遍历 metrics 寻找该 slug 的成功记录
            # metrics 结构: {"1": {"slug": "...", "status": "SUCCESS", ...}}
            for seq, data in pipeline.metrics.items():
                if data.get("slug") == slug and data.get("status") == "SUCCESS":
                    return True
            return False

        return False
