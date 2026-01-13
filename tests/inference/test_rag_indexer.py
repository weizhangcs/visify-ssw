import logging
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, override_settings
from django.test.runner import DiscoverRunner

from apps.common.schemas.narrative_dataset import NarrativeDataset
from apps.inference.services.rag_indexer import ProjectRAGService

logger = logging.getLogger(__name__)

# =============================================================================
# [配置] 请在此处填写您导出的真实 JSON 文件路径
# =============================================================================
# 示例: r"D:\DevProjects\PyCharmProjects\visify-ssw\output.json"
REAL_DATA_PATH = r"D:\DevProjects\PyCharmProjects\visify-ssw\media_root\annotation\615dea63-2e74-474e-bad1-1701294b4d3c\blueprints\blueprint_615dea63-2e74-474e_cfNEwSS.json"  # noqa: E501

# 创建一个临时目录用于存放生成的向量索引，避免污染真实环境
TEMP_MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class RealDataRagTest(SimpleTestCase):
    """
    [集成测试] 使用真实 Annotation Workbench 产出的数据测试 RAG 流程
    目的：验证 Workbench 数据质量以及 RAG 检索的准确性
    """

    def setUp(self):
        self.json_path = Path(REAL_DATA_PATH)

        # 自动寻找逻辑：如果指定路径不存在，尝试在当前项目根目录找 .json
        if not self.json_path.exists():
            cwd_files = list(Path(".").glob("*.json"))
            if cwd_files:
                self.json_path = cwd_files[0]
                print(f"[Setup] Auto-detected JSON file: {self.json_path}")

        if not self.json_path.exists():
            self.skipTest(
                f"Real data file not found at: {REAL_DATA_PATH}. Please update REAL_DATA_PATH in the test file."
            )

        print(f"\n[Setup] Loading real data from: {self.json_path}")

        # 加载并校验数据
        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                content = f.read()
                # 使用 Pydantic 进行反序列化，这本身就是对 Workbench 产出格式的一次强校验
                self.dataset = NarrativeDataset.model_validate_json(content)

            self.project_id = str(self.dataset.project_uuid)

            scene_count = len(self.dataset.scenes)
            print("[Setup] Dataset loaded successfully.")
            print(f"        Project: {self.dataset.project_metadata.project_name}")
            print(f"        Scenes: {scene_count}")

            if scene_count == 0:
                self.fail("Dataset contains 0 scenes. Please check Annotation Workbench output.")

        except Exception as e:
            self.fail(f"Failed to parse JSON into NarrativeDataset: {e}")

    def tearDown(self):
        if Path(TEMP_MEDIA_ROOT).exists():
            shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def test_real_data_rag_flow(self):
        # Patch INDEX_ROOT 指向临时目录
        with mock.patch(
            "apps.inference.services.rag_indexer.ProjectRAGService.INDEX_ROOT",
            Path(TEMP_MEDIA_ROOT) / "inference" / "rag_indices",
        ):
            # 1. 构建索引
            print("\n[Step 1] Building Index...")
            try:
                index_path = ProjectRAGService.build_index(self.project_id, self.dataset)
            except RuntimeError as e:
                self.skipTest(f"Skipping RAG test: {e} (Missing dependencies)")

            self.assertTrue(Path(index_path).exists(), "Index file (.pkl) should be created")
            print(f"        Index saved to: {index_path}")

            # 2. 执行检索测试
            # 这里定义一些通用的 Query，你可以根据你的视频内容修改这些词
            queries = ["两个人争吵", "安静的夜晚", "激烈的动作场面", "室内对话", "悲伤的情绪"]  # 冲突/对白  # 氛围  # 动作  # 场景类型  # 情绪

            print("\n[Step 2] Performing Search Tests (Top 2)...")

            for q in queries:
                print(f"\n   Query: [{q}]")
                results = ProjectRAGService.search(self.project_id, q, top_k=2)

                if not results:
                    print("   -> No results found.")
                    continue

                for i, res in enumerate(results):
                    print(
                        f"   -> Rank {i+1} (Score: {res['score']:.4f}) | Scene Local ID: {res['scene_local_id']}"  # noqa: E221,E226,E231,E501
                    )

                    # 回溯并打印场景详情，验证数据质量
                    scene_uuid = res.get("scene_uuid")
                    if scene_uuid and self.dataset.scenes:
                        scene = self.dataset.scenes.get(scene_uuid)
                        if scene:
                            print(f"      Summary: {scene.narrative_summary[:60]}...")
                            print(f"      Mood:    {scene.mood_and_atmosphere}")  # noqa: E241
                            if scene.dialogues:
                                first_line = f"{scene.dialogues[0].speaker}: {scene.dialogues[0].content}"
                                print(f"      Dialog:  {first_line[:60]}...")  # noqa: E241


class NoDbTestRunner(DiscoverRunner):
    """
    自定义 TestRunner，跳过数据库创建和系统检查。
    用于在数据库不可用的环境下运行纯逻辑测试 (SimpleTestCase)。
    """

    def setup_databases(self, **kwargs):
        return None

    def teardown_databases(self, old_config, **kwargs):
        pass

    def run_checks(self, databases):
        pass
