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


def run_visual_flow_test():
    print("=" * 60)
    print("🚀 Atomflow Refinery - Visual Micro LLM 流程验证")
    print("=" * 60)

    # 1. 物理落地规则 (Rule)
    # 专注于 frame_extract 和 frame_probe 两个步骤
    rules_json = [
        {"seq": 1, "unit_slug": "frame_probe", "name": "关键检测", "obligation": "REQUIRED"},
        {"seq": 2, "unit_slug": "sync", "name": "云端同步", "obligation": "REQUIRED", "dependence": [1]},
        {"seq": 3, "unit_slug": "visual_analyzer", "name": "视觉识别", "obligation": "REQUIRED", "dependence": [2]},
    ]

    rule, _ = RefineryAtomRule.objects.update_or_create(
        slug="refinery_visual_flow_v4",
        defaults={"name": "Refinery 视觉流程规则 V4", "rules_config": rules_json, "mode": "PROD"},
    )
    print(f"[*] 规则已就绪: {rule.slug} (步骤数: {rule.step_count})")

    # 2. 准备业务物料 (Material)
    # 直接使用提供的 material_id
    material_id = "aab9252f-ba90-4762-8537-2b79a0cb38fb"
    try:
        material = Material.objects.get(id=material_id)
    except Material.DoesNotExist:
        print(f"❌ 错误：Material ID '{material_id}' 不存在。请确保该物料已存在且包含 proxy_video 和 visual_slices。")
        return

    # 确保 Material 具备运行这两个步骤的先决条件
    if not material.proxy_video:
        print(f"❌ 错误：Material '{material_id}' 缺少 proxy_video。请先运行 Transcode 步骤。")
        return
    if not material.visual_slices:
        print(f"❌ 错误：Material '{material_id}' 缺少 visual_slices。请先运行 Slicing 步骤。")
        return

    print(f"[*] 选中 Material: {material.id} (Media: {material.media.title})")

    # 3. [关键步骤] 物理落地执行轨迹 (Pipeline)
    # 复用或更新已存在的 Pipeline，并更新其规则
    pipeline, created = RefineryAtomPipeline.objects.update_or_create(
        target_id=str(material.id),
        defaults={
            "name": f"Refinery-Visual-{int(time.time())}",
            "rule": rule,
            "material": material,
            "status": "PENDING",
            "metrics": {},  # 清空 metrics 以便重新测试
            "error_log": "",
        },
    )
    print(f"[*] Pipeline {'创建新' if created else '复用并更新'}: {pipeline.id}")

    # 4. 正式点火
    print("\n🔥[Action] 正在派发初始节点 (Roots)...")

    root_steps = [s for s in rules_json if not s.get("dependence")]
    for step in root_steps:
        print(f"-> 派发: {step['name']} (Seq: {step['seq']})")
        RefineryAtomScheduler.dispatch(target_id=str(pipeline.id), step_config=step)

    print("✅ 任务已派发，开始链路轮询监控 (Max 600s)...")
    print("-" * 60)

    # 5. 链路轮询监控 (Polling)
    max_retries = 300  # 300 * 2s = 600s 超时
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
            # 打印关键结果
            print(f"Material Visual Slices count: {len(material.visual_slices)}")
            if material.visual_slices and material.visual_slices[0].get("visual_contents", {}).get("frames"):
                first_frame = material.visual_slices[0]["visual_contents"]["frames"][0]
                print(
                    f"First Slice First Frame: Path={first_frame['path']}, Quality={first_frame.get('quality_score')}"
                )
            return

    print("\n⚠️ 测试超时！Worker 可能未响应或处理过慢。")
    print("请检查 Celery Worker 日志排查 AttributeError 或其他异常。")


if __name__ == "__main__":
    run_visual_flow_test()
