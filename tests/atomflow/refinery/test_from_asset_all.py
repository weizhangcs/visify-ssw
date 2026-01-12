import os
import sys
import time
from pathlib import Path

import django

# 1. 环境初始化
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "visify_ssw.settings")
django.setup()

from apps.atomflow.refinery.models import Material, RefineryAtomPipeline, RefineryAtomRule  # noqa: E402
from apps.atomflow.refinery.scheduler import RefineryAtomScheduler  # noqa: E402
from apps.media_assets.models import Asset, Media  # noqa: E402


def run_asset_flow_test():
    print("=" * 60)
    print("🚀 Atomflow Refinery - Asset 级多集并行与栅栏机制验证")
    print("=" * 60)

    # 1. 定义包含 Barrier 的规则
    # 注意：seq 6 是 ASSET 级别的栅栏
    rules_json = [
        {"seq": 1, "unit_slug": "transcode", "name": "原子转码", "obligation": "REQUIRED"},
        {"seq": 2, "unit_slug": "probe", "name": "原子探测", "obligation": "REQUIRED", "dependence": [1]},
        {"seq": 3, "unit_slug": "generate_hls", "name": "HLS切片", "obligation": "REQUIRED", "dependence": [1]},
        {"seq": 4, "unit_slug": "text_analyze", "name": "文本分析", "obligation": "REQUIRED", "dependence": [3]},
        {"seq": 5, "unit_slug": "audio_analyze", "name": "声纹分析", "obligation": "REQUIRED", "dependence": [4]},
        # [Barrier] 全局角色统筹
        {
            "seq": 6,
            "unit_slug": "global_character_refine",
            "name": "全剧角色统筹",
            "obligation": "REQUIRED",
            "dependence": [5],
            "scope": "ASSET",
        },
        # [Resume] 恢复并行
        {"seq": 7, "unit_slug": "slice", "name": "视觉切片", "obligation": "REQUIRED", "dependence": [6]},
        {"seq": 8, "unit_slug": "frame_extract", "name": "关键帧提取", "obligation": "REQUIRED", "dependence": [7]},
        {"seq": 9, "unit_slug": "frame_probe", "name": "关键帧检测", "obligation": "REQUIRED", "dependence": [8]},
        {"seq": 10, "unit_slug": "synchronize", "name": "云端同步", "obligation": "REQUIRED", "dependence": [9]},
        {"seq": 11, "unit_slug": "analyze_visual", "name": "视觉识别", "obligation": "REQUIRED", "dependence": [10]},
        {"seq": 12, "unit_slug": "analyze_slice", "name": "切片分析", "obligation": "REQUIRED", "dependence": [11]},
        {"seq": 13, "unit_slug": "regroup_slice", "name": "切片聚类", "obligation": "REQUIRED", "dependence": [12]},
        {"seq": 14, "unit_slug": "vector_index", "name": "向量索引", "obligation": "REQUIRED", "dependence": [13]},
    ]

    rule, _ = RefineryAtomRule.objects.update_or_create(
        slug="refinery_asset_barrier_test",
        defaults={"name": "Refinery Asset Barrier Test Rule", "rules_config": rules_json, "mode": "PROD"},
    )
    print(f"[*] 规则已就绪: {rule.slug}")

    # 2. 准备测试数据 (Asset + Multiple Media)
    # [修正] 使用真实数据：查找系统中已存在的 Asset
    print("🔍 正在查找符合条件的测试 Asset (Media >= 2)...")

    target_asset = None
    episodes = []

    # 遍历查找包含至少 2 个 Media 的 Asset
    # 简单遍历，找到第一个满足条件的 Asset 即可
    for asset in Asset.objects.all():
        medias = list(Media.objects.filter(asset=asset).order_by("sequence_number"))
        if len(medias) >= 2:
            target_asset = asset
            episodes = medias
            break

    if not target_asset:
        print("❌ 错误：未找到包含至少 2 集 Media 的 Asset。")
        print("请先在后台创建一个 Asset，并上传至少 2 个视频文件，然后再次运行此测试。")
        return

    print(f"[*] 选中测试 Asset: {target_asset.title} ({target_asset.id})")
    print(f"[*] 包含 {len(episodes)} 集 Media")

    # 3. 创建 Pipeline 并点火
    pipelines = []
    for media in episodes:
        material, _ = Material.objects.get_or_create(media=media)

        # 清理旧数据 (虽然是新 Media，但防御性编程)
        if hasattr(material, "pipeline"):
            material.pipeline.delete()

        pipeline = RefineryAtomPipeline.objects.create(
            name=f"Pipe-{media.title}",
            rule=rule,
            target_id=str(material.id),
            material=material,
            status="PENDING",
        )
        pipelines.append(pipeline)

    print(f"\n🔥[Action] 正在并发启动 {len(pipelines)} 条流水线...")

    root_steps = [s for s in rules_json if not s.get("dependence")]
    for p in pipelines:
        for step in root_steps:
            RefineryAtomScheduler.dispatch(target_id=str(p.id), step_config=step)

    print("✅ 所有任务已派发，开始全局监控...")
    print("-" * 60)

    # 4. 监控循环
    max_retries = 2000  # 2000 * 5s = ~2.7 hours (足够跑完全流程)
    target_steps = {r["unit_slug"] for r in rules_json}

    for i in range(max_retries):
        time.sleep(5)

        # 收集所有 Pipeline 的状态
        all_finished = True
        waiting_count = 0
        success_count = 0
        failed_count = 0

        for p in pipelines:
            p.refresh_from_db()
            metrics = p.metrics or {}

            # 检查 Barrier 状态 (seq 6)
            barrier_status = metrics.get("6", {}).get("status", "PENDING")
            completed_slugs = {v.get("slug") for v in metrics.values() if v.get("status") == "SUCCESS"}

            if p.status == "FAILED":
                failed_count += 1
                print(f"\n❌ Pipeline {p.id} Failed! Error: {p.error_log}")
            elif not target_steps.issubset(completed_slugs):
                all_finished = False
            else:
                success_count += 1

            if barrier_status == "WAITING":
                waiting_count += 1

        print(
            f"[{i+1}] Progress: {success_count}/{len(pipelines)} Done | Waiting at Barrier: {waiting_count} | Failed: {failed_count}"  # noqa: E226, E501
        )

        if failed_count > 0:
            print("\n❌ 测试失败：有 Pipeline 报错中断。")
            return

        if all_finished:
            print("\n🎉 全局测试成功！所有集数均已完成全流程。")

            # 验证结果
            for media in episodes:
                mat = Material.objects.get(media=media)
                print(f"Media {media.title}: Identified Characters = {len(mat.identified_characters)}")
            return

    print("\n⚠️ 测试超时！")


if __name__ == "__main__":
    run_asset_flow_test()
