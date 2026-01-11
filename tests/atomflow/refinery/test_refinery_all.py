import os
import sys
import time
from pathlib import Path

import django

# 1. 环境初始化 (保持不变)
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "visify_ssw.settings")
django.setup()

# [核心修改] 引入新实现的模型
from apps.atomflow.refinery.models import Material, RefineryAtomPipeline, RefineryAtomRule  # noqa: E402
from apps.atomflow.refinery.scheduler import RefineryAtomScheduler  # noqa: E402
from apps.media_assets.models import Media  # noqa: E402


def run_flow_test():
    print("=" * 60)
    print("🚀 Atomflow Refinery - 真实 Pipeline 流程验证")
    print("=" * 60)

    # 1. 物理落地规则 (Rule)
    # 算子化框架必须依赖配置，我们先在数据库创建一个临时的测试规则
    # 全量编排：Transcode -> Probe -> HLS -> Text -> Char -> Slicing -> Frame -> Sync
    rules_json = [
        {"seq": 1, "unit_slug": "transcode", "name": "原子转码", "obligation": "REQUIRED"},
        {"seq": 2, "unit_slug": "probe", "name": "原子探测", "obligation": "REQUIRED", "dependence": [1]},
        {"seq": 3, "unit_slug": "hls", "name": "HLS切片", "obligation": "REQUIRED", "dependence": [1]},
        {"seq": 4, "unit_slug": "text_analyze", "name": "文本分析", "obligation": "REQUIRED", "dependence": [3]},
        {"seq": 5, "unit_slug": "audio_analyze", "name": "声纹分析", "obligation": "REQUIRED", "dependence": [4]},
        {"seq": 6, "unit_slug": "character_refine", "name": "角色精修", "obligation": "REQUIRED", "dependence": [5]},
        {"seq": 7, "unit_slug": "slicing", "name": "视觉切片", "obligation": "REQUIRED", "dependence": [6]},
        {"seq": 8, "unit_slug": "frame_extract", "name": "关键帧提取", "obligation": "REQUIRED", "dependence": [7]},
        {"seq": 9, "unit_slug": "frame_probe", "name": "关键帧检测", "obligation": "REQUIRED", "dependence": [8]},
        {"seq": 10, "unit_slug": "sync", "name": "云端同步", "obligation": "REQUIRED", "dependence": [9]},
        {"seq": 11, "unit_slug": "visual_analyzer", "name": "视觉识别", "obligation": "REQUIRED", "dependence": [10]},
        {"seq": 12, "unit_slug": "slice_analyzer", "name": "切片分析", "obligation": "REQUIRED", "dependence": [11]},
        {"seq": 13, "unit_slug": "slice_regrouper", "name": "切片聚类", "obligation": "REQUIRED", "dependence": [12]},
        {"seq": 14, "unit_slug": "vector_index", "name": "向量索引", "obligation": "REQUIRED", "dependence": [12]},
    ]

    rule, _ = RefineryAtomRule.objects.update_or_create(
        slug="refinery_full_flow_v1",
        defaults={"name": "Refinery 全量编排规则 V2", "rules_config": rules_json, "mode": "PROD"},
    )
    print(f"[*] 规则已就绪: {rule.slug} (步骤数: {rule.step_count})")

    # 2. 准备业务物料 (Material)
    # 自动寻找一个有源视频的 Media，如果未关联 Material 则自动创建
    media = Media.objects.get(title="001")
    if not media:
        print("❌ 错误：Media 库中没有可用的视频资源。请先在系统中上传至少一个视频文件。")
        return

    material, created = Material.objects.get_or_create(media=media)
    print(f"[*] 选中 Media: {media.title} ({media.id})")
    print(f"[*] {'创建新' if created else '复用'} Material: {material.id}")

    # 清理旧状态以便重测 (可选)
    # material.proxy_video = ""
    # material.hls_playlist = ""
    # material.save()

    # 3. [关键步骤] 物理落地执行轨迹 (Pipeline)
    # 检查是否已存在 Pipeline，如果存在则复用或清理
    # 由于是一对一关系，如果已存在，我们需要先删除旧的，或者复用它
    # 注意：为了测试准确性，建议每次都清理旧的 Pipeline 记录
    if hasattr(material, "pipeline"):
        print(f"[*] 检测到旧 Pipeline {material.pipeline.id}，正在清理...")
        material.pipeline.delete()

    pipeline = RefineryAtomPipeline.objects.create(
        name=f"Refinery-{int(time.time())}",
        rule=rule,
        target_id=str(material.id),  # 记录该 Pipeline 属于哪个 Material
        material=material,  # [修正] 显式关联 OneToOneField
        status="PENDING",
    )
    print(f"[*] Pipeline 已创建: {pipeline.id}")
    print(f"[*] 目标物料: {material.id}")

    # 4. 正式点火
    print("\n🔥[Action] 正在派发初始节点 (Roots)...")

    # [Fix] 寻找所有无依赖的根节点进行派发 (Transcode 和 Text Analyze)
    root_steps = [s for s in rules_json if not s.get("dependence")]
    for step in root_steps:
        print(f"-> 派发: {step['name']} (Seq: {step['seq']})")
        RefineryAtomScheduler.dispatch(target_id=str(pipeline.id), step_config=step)

    print("✅ 任务已派发，开始链路轮询监控 (Max 600s)...")
    print("-" * 60)

    # 5. 链路轮询监控 (Polling)
    max_retries = 10000  # 10000 * 5s = 50000s 超时
    target_steps = {r["unit_slug"] for r in rules_json}

    for i in range(max_retries):
        time.sleep(5)

        # 刷新数据库状态
        pipeline.refresh_from_db()
        material = Material.objects.get(id=material.id)

        # 获取当前完成的步骤
        metrics = pipeline.metrics or {}
        completed_slugs = {v.get("slug") for v in metrics.values() if v.get("status") == "SUCCESS"}

        # 打印进度条
        progress = f"[{i+1}/{max_retries}] Pipeline: {pipeline.status: <10} | Steps: {len(completed_slugs)}/{len(target_steps)} {list(completed_slugs)}"  # noqa: E501,E226
        print(progress)

        # 失败判定
        if pipeline.status == "FAILED":
            print("\n❌ 链路中断！Pipeline 状态为 FAILED")
            print(f"错误日志: {pipeline.error_log}")
            return

        # 成功判定
        if target_steps.issubset(completed_slugs):
            print("\n🎉 链路验证成功！所有步骤均已完成。")
            print(f"Proxy Path: {material.proxy_video}")
            print(f"HLS Path: {material.hls_playlist}")
            print(f"Duration: {material.duration}")
            print(f"Vector Index: {material.local_vector_index_path}")
            return

    print("\n⚠️ 测试超时！Worker 可能未响应或处理过慢。")
    print("请检查 Celery Worker 日志排查 AttributeError 或其他异常。")


if __name__ == "__main__":
    run_flow_test()
