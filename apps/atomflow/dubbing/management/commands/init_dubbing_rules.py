from django.core.management.base import BaseCommand

from apps.atomflow.dubbing.models import DubbingAtomRule, DubbingAtomUnit


class Command(BaseCommand):
    help = "Initialize Dubbing Atomflow Rules and Units"

    def handle(self, *args, **options):
        self.stdout.write("Initializing Dubbing Atomflow...")

        # 1. 注册原子算子 (Units)
        # 对应 task_registry.py 中的 SERVICE_REGISTRY
        units_data = [
            {
                "slug": "audio_separation",
                "name": "人声分离 (BS-Roformer)",
                "description": "使用 BS-Roformer 模型分离人声与伴奏",
                "execution_mode": "ASYNC",
                "resource_class": "AI",
            },
            {
                "slug": "audio_gating",
                "name": "语义门控 (Gating)",
                "description": "结合 YamNet 和 Silero VAD 生成处理掩码",
                "execution_mode": "ASYNC",
                "resource_class": "AI",
            },
            {
                "slug": "audio_enhancement",
                "name": "人声增强 (DeepFilterNet)",
                "description": "应用掩码并进行降噪增强",
                "execution_mode": "ASYNC",
                "resource_class": "AI",
            },
            {
                "slug": "audio_material_build",
                "name": "素材轨构建 (M&E)",
                "description": "构建背景素材轨 (Music & Effects)",
                "execution_mode": "ASYNC",
                "resource_class": "COMPUTING",
            },
            {
                "slug": "audio_perception_analyze",
                "name": "感知分析 (ASR+Features)",
                "description": "提取 ASR 文本及声学特征",
                "execution_mode": "ASYNC",
                "resource_class": "AI",
            },
            {
                "slug": "video_ocr",
                "name": "视频OCR (RapidOCR)",
                "description": "提取硬字幕并生成索引",
                "execution_mode": "ASYNC",
                "resource_class": "AI",
            },
            {
                "slug": "video_inpainting",
                "name": "视频去字幕 (LaMa)",
                "description": "基于OCR掩码擦除硬字幕",
                "execution_mode": "ASYNC",
                "resource_class": "AI",
            },
            {
                "slug": "visual_analysis",
                "name": "视觉分析 (InsightFace)",
                "description": "人脸检测、识别与聚类",
                "execution_mode": "ASYNC",
                "resource_class": "AI",
            },
            {
                "slug": "audio_visual_fusion",
                "name": "视听融合 (Active Speaker)",
                "description": "基于唇形同步判断当前说话人",
                "execution_mode": "ASYNC",
                "resource_class": "AI",
            },
            {
                "slug": "script_refinement",
                "name": "脚本精修 (VSS Cloud)",
                "description": "基于ASR和OCR结果进行多模态脚本校对",
                "execution_mode": "ASYNC",
                "resource_class": "NETWORK",
            },
        ]

        for u_data in units_data:
            unit, created = DubbingAtomUnit.objects.update_or_create(slug=u_data["slug"], defaults=u_data)
            status = "Created" if created else "Updated"
            self.stdout.write(f"  [{status}] Unit: {unit.name}")

        # 2. 定义编排规则 (Rule)
        # 定义 DAG 依赖关系
        rule_config = [
            {"seq": 1, "unit_slug": "audio_separation", "name": "Step 1: Separation", "dependence": []},  # 入口节点
            {"seq": 2, "unit_slug": "audio_gating", "name": "Step 2: Gating", "dependence": [1]},  # 依赖分离结果
            {
                "seq": 3,
                "unit_slug": "audio_enhancement",
                "name": "Step 3: Enhancement",
                "dependence": [2],  # 依赖 Gating Mask
            },
            {
                "seq": 4,
                "unit_slug": "audio_material_build",
                "name": "Step 4: Material Track",
                "dependence": [3],  # 依赖增强后的人声(用于残差计算)和Mask
            },
            {
                "seq": 5,
                "unit_slug": "audio_perception_analyze",
                "name": "Step 6: Analysis",  # 原脚本 Step 5 是 ffmpeg 转换，已内聚
                "dependence": [4],  # 强制串行化：Step 4 完成后再执行，避免并发调度导致的重复执行
            },
            # --- Video Pipeline Integration ---
            {"seq": 6, "unit_slug": "visual_analysis", "name": "Step 1: Visual Analysis", "dependence": [5]},
            {
                "seq": 7,
                "unit_slug": "audio_visual_fusion",
                "name": "Step 2: Audio-Visual Fusion",
                "dependence": [6],  # 隐式依赖 Rule 1 的 Perception 结果
            },
        ]

        # Rule 2: Video Pipeline
        rule_video_config = [
            {"seq": 1, "unit_slug": "audio_separation", "name": "Step 1: Separation", "dependence": []},  # 入口节点
            {"seq": 2, "unit_slug": "audio_gating", "name": "Step 2: Gating", "dependence": [1]},  # 依赖分离结果
            {
                "seq": 3,
                "unit_slug": "audio_enhancement",
                "name": "Step 3: Enhancement",
                "dependence": [2],  # 依赖 Gating Mask
            },
            {
                "seq": 4,
                "unit_slug": "audio_material_build",
                "name": "Step 4: Material Track",
                "dependence": [3],  # 依赖增强后的人声(用于残差计算)和Mask
            },
            {
                "seq": 5,
                "unit_slug": "audio_perception_analyze",
                "name": "Step 6: Analysis",  # 原脚本 Step 5 是 ffmpeg 转换，已内聚
                "dependence": [4],  # 强制串行化：Step 4 完成后再执行，避免并发调度导致的重复执行
            },
        ]

        # Rule 3: Fusion Pipeline
        rule_fusion_config = [
            {"seq": 1, "unit_slug": "visual_analysis", "name": "Step 1: Visual Analysis", "dependence": []},
            {
                "seq": 2,
                "unit_slug": "audio_visual_fusion",
                "name": "Step 2: Audio-Visual Fusion",
                "dependence": [1],  # 隐式依赖 Rule 1 的 Perception 结果
            },
        ]

        # Rule 4: Integrated Pipeline (All-in-One)
        rule_integrated_config = [
            # --- Audio Track ---
            {"seq": 1, "unit_slug": "audio_separation", "name": "Step 1: Separation", "dependence": []},
            {"seq": 2, "unit_slug": "audio_gating", "name": "Step 2: Gating", "dependence": [1]},
            {"seq": 3, "unit_slug": "audio_enhancement", "name": "Step 3: Enhancement", "dependence": [2]},
            {"seq": 4, "unit_slug": "audio_material_build", "name": "Step 4: Material Track", "dependence": [3]},
            {"seq": 5, "unit_slug": "audio_perception_analyze", "name": "Step 5: Audio Analysis", "dependence": [4]},
            # --- Video Track (Subtitle Removal) ---
            {
                "seq": 6,
                "unit_slug": "video_ocr",
                "name": "Step 6: Video OCR",
                "dependence": [5],  # Uses audio gating mask
            },
            {"seq": 7, "unit_slug": "video_inpainting", "name": "Step 7: Video Inpainting", "dependence": [6]},
            # --- Script Track ---
            {
                "seq": 8,
                "unit_slug": "script_refinement",
                "name": "Step 10: Script Refinement",
                "dependence": [7],  # Needs Audio Analysis & OCR
            },
            {"seq": 9, "unit_slug": "visual_analysis", "name": "Step 1: Visual Analysis", "dependence": [8]},
            {
                "seq": 10,
                "unit_slug": "audio_visual_fusion",
                "name": "Step 2: Audio-Visual Fusion",
                "dependence": [9],  # 隐式依赖 Rule 1 的 Perception 结果
            },
        ]

        rule, created = DubbingAtomRule.objects.update_or_create(
            slug="dubbing_standard_v1",
            defaults={
                "name": "标准配音预处理流程 V1",
                "description": "Audio (Sep->Gate->Enh->Mat->Ana) + Video (OCR->Inpaint)",
                "mode": "PROD",
                "rules_config": rule_config,
            },
        )
        self.stdout.write(f"  [Saved] Rule: {rule.name}")

        rule_v2, created_v2 = DubbingAtomRule.objects.update_or_create(
            slug="dubbing_video_v1",
            defaults={
                "name": "视频去字幕流程 V1",
                "description": "OCR -> Inpainting",
                "mode": "PROD",
                "rules_config": rule_video_config,
            },
        )
        self.stdout.write(f"  [Saved] Rule: {rule_v2.name}")

        rule_v3, created_v3 = DubbingAtomRule.objects.update_or_create(
            slug="dubbing_fusion_v1",
            defaults={
                "name": "视听融合流程 V1",
                "description": "Visual -> Fusion (Requires Audio Pipeline)",
                "mode": "PROD",
                "rules_config": rule_fusion_config,
            },
        )
        self.stdout.write(f"  [Saved] Rule: {rule_v3.name}")

        rule_v4, created_v4 = DubbingAtomRule.objects.update_or_create(
            slug="dubbing_integrated_v1",
            defaults={
                "name": "全链路整合流程 V1",
                "description": "Audio + Video (OCR/Inpaint) + Visual (Face/Fusion) + Script (Refinement)",
                "mode": "PROD",
                "rules_config": rule_integrated_config,
            },
        )
        self.stdout.write(f"  [Saved] Rule: {rule_v4.name}")
        self.stdout.write(self.style.SUCCESS("Done."))
