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


def run_flow_test():
    print("=" * 60)
    print("🚀 Atomflow Refinery - 真实 Pipeline 流程验证")
    print("=" * 60)

    # 1. 物理落地规则 (Rule)
    # 算子化框架必须依赖配置，我们先在数据库创建一个临时的测试规则
    # [Schema验证编排] 聚焦于 Step 1 & 2 的变更验证
    # 假设 Proxy 已存在，跳过 Transcode
    rules_json = [
        {"seq": 1, "unit_slug": "transcode", "name": "原子转码", "obligation": "REQUIRED"},
        {"seq": 2, "unit_slug": "probe", "name": "原子探测", "obligation": "REQUIRED", "dependence": [1]},
        {"seq": 3, "unit_slug": "generate_hls", "name": "HLS切片", "obligation": "REQUIRED", "dependence": [1]},
        {"seq": 4, "unit_slug": "text_analyze", "name": "文本分析", "obligation": "REQUIRED", "dependence": [3]},
        {"seq": 5, "unit_slug": "audio_analyze", "name": "声纹分析", "obligation": "REQUIRED", "dependence": [4]},
        {
            "seq": 6,
            "unit_slug": "global_character_refine",
            "name": "全剧角色统筹",
            "obligation": "REQUIRED",
            "scope": "ASSET",
            "dependence": [5],
        },  # noqa: E501
    ]

    rule, _ = RefineryAtomRule.objects.update_or_create(
        slug="refinery_schema_test_v1",
        defaults={"name": "Refinery Schema验证规则", "rules_config": rules_json, "mode": "PROD"},
    )
    print(f"[*] 规则已就绪: {rule.slug} (步骤数: {rule.step_count})")

    # 2. 准备业务物料 (Material)
    # 直接使用提供的 material_id
    material_id = "8086af2f-e1e6-4c46-8d4c-ba6278aee84c"
    try:
        material = Material.objects.get(id=material_id)
    except Material.DoesNotExist:
        print(f"❌ 错误：Material ID '{material_id}' 不存在。请确保该物料已存在且包含 proxy_video 和 visual_slices。")
        return

    print(f"[*] 选中 Material: {material.id} (Media: {material.media.title})")

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
    max_retries = 1000  # 300 * 2s = 600s 超时
    target_steps = {r["unit_slug"] for r in rules_json}

    for i in range(max_retries):
        time.sleep(2)

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
            print("-" * 30)
            print(f"Dialogues Count: {len(material.dialogues)}")
            print(f"Slices Count: {len(material.slices)}")
            print(f"Frames Count (Flat): {len(material.frames)}")
            if material.slices:
                print(f"Sample Slice Refs: DialogueIDs={len(material.slices[0].get('dialogue_ids', []))}")
                print(f"Slice Analysis: {bool(material.slices[0].get('slice_analysis'))}")
            print(f"Scenes Count: {len(material.scenes)}")
            print(f"Vector Index Path: {material.slice_vector_index_path}")
            print("-" * 30)
            return

    print("\n⚠️ 测试超时！Worker 可能未响应或处理过慢。")
    print("请检查 Celery Worker 日志排查 AttributeError 或其他异常。")


if __name__ == "__main__":
    run_flow_test()
