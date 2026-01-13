import logging
import pickle
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase
from django.test.runner import DiscoverRunner

from apps.common.schemas.narrative_dataset import NarrativeDataset
from apps.inference.services.rag_indexer import ProjectRAGService

logger = logging.getLogger(__name__)

# =============================================================================
# [配置区]
# =============================================================================
# 1. 输入：真实 Blueprint JSON 路径
REAL_DATA_PATH = r"D:\DevProjects\PyCharmProjects\visify-ssw\media_root\annotation\615dea63-2e74-474e-bad1-1701294b4d3c\blueprints\blueprint_615dea63-2e74-474e_cfNEwSS.json"  # noqa: E501

# 2. 输出：测试产物存放目录 (非临时，持久化以便人工检查)
OUTPUT_DIR = Path(r"D:\DevProjects\PyCharmProjects\visify-ssw\tests\testdata\tmp")

# 3. 模拟 Query：用于生成 RAG Context 的测试问题
TEST_QUERIES = [
    {
        # [优化案例] 梳理全剧感情线
        # 技巧 1: text 使用具体的语义描述，而不是 "所有的场景"
        # 技巧 2: top_k 设为 20，确保召回所有相关场景 (因为总共只有 14 个)
        "name": "full_emotional_arc",
        "text": "男女主角之间的情感互动，包括初遇、暧昧、误会、争吵和和解",
        "narrative_focus": "梳理全剧的感情线发展脉络",
        "top_k": 20,
    }
]


class NoDbTestRunner(DiscoverRunner):
    """跳过数据库检查的运行器"""

    def setup_databases(self, **kwargs):
        return None

    def teardown_databases(self, old_config, **kwargs):
        pass

    def run_checks(self, databases):
        pass


class RagWorkflowTest(SimpleTestCase):
    """
    [RAG 生产级验证工作流]
    Step 1: 生成索引并导出语料 (Corpus) -> 验证切片颗粒度和信息量
    Step 2: 执行检索并生成 Prompt Context -> 验证业务推理能力
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # 确保输出目录存在
        if not OUTPUT_DIR.exists():
            OUTPUT_DIR.mkdir(parents=True)

        # 加载数据
        cls.json_path = Path(REAL_DATA_PATH)
        if not cls.json_path.exists():
            raise FileNotFoundError(f"Real data not found: {REAL_DATA_PATH}")

        with open(cls.json_path, "r", encoding="utf-8") as f:
            cls.dataset = NarrativeDataset.model_validate_json(f.read())

        cls.project_id = str(cls.dataset.project_uuid)
        print(
            f"\n[Init] Loaded Project: {cls.dataset.project_metadata.project_name} ({len(cls.dataset.scenes)} scenes)"
        )
        print(f"[Init] Output Directory: {OUTPUT_DIR}")

    def test_step_1_generate_index_and_corpus(self):
        """
        [Step 2.a] 独立创建 PKL，并写入富文本语料供检查
        """
        print("\n>>> Step 1: Generating Index & Debug Corpus...")

        # 1. Mock INDEX_ROOT 到测试输出目录
        # 这样生成的 rag_indices 文件夹会出现在 tests/testdata/tmp/inference/rag_indices 下
        mock_root = OUTPUT_DIR / "inference" / "rag_indices"

        with mock.patch("apps.inference.services.rag_indexer.ProjectRAGService.INDEX_ROOT", mock_root):
            # 执行构建
            index_path_str = ProjectRAGService.build_index(self.project_id, self.dataset)
            index_path = Path(index_path_str)

            self.assertTrue(index_path.exists())
            print(f"    [Artifact] Index PKL saved to: {index_path}")

            # 2. 读取 PKL 中的 Metadata (包含 raw_text)
            with open(index_path, "rb") as f:
                data = pickle.load(f)
                metadata = data["metadata"]

            # 3. 导出为可读文本文件 (Corpus Debug)
            corpus_file = OUTPUT_DIR / "step_2a_corpus_debug.txt"
            with open(corpus_file, "w", encoding="utf-8") as f:
                f.write(f"Project: {self.dataset.project_metadata.project_name}\n")
                f.write(f"Total Scenes: {len(metadata)}\n")
                f.write("=" * 80 + "\n\n")

                for item in metadata:
                    f.write(f"[Scene Local ID: {item['scene_local_id']}] ({item['start_time']} - {item['end_time']})\n")
                    f.write("-" * 40 + "\n")
                    f.write(item["raw_text"])
                    f.write("\n" + "=" * 80 + "\n\n")

            print(f"    [Artifact] Rich Text Corpus saved to: {corpus_file}")
            print("    -> 请检查该文件，确认每个场景的文本描述是否包含足够的信息量 (剧情、氛围、对白)。")

    def test_step_2_query_and_generate_context(self):
        """
        [Step 2.b] 独立配置 Query，生成 RAG Context
        """
        print("\n>>> Step 2: Running Queries & Generating RAG Context...")

        mock_root = OUTPUT_DIR / "inference" / "rag_indices"

        # 确保索引已存在 (依赖 Step 1，或者手动跑一次)
        # 为了独立性，这里如果不存在会尝试重建，但在测试套件中通常按顺序执行
        if not (mock_root / self.project_id / "scene_index.pkl").exists():
            with mock.patch("apps.inference.services.rag_indexer.ProjectRAGService.INDEX_ROOT", mock_root):
                ProjectRAGService.build_index(self.project_id, self.dataset)

        with mock.patch("apps.inference.services.rag_indexer.ProjectRAGService.INDEX_ROOT", mock_root):
            for q_cfg in TEST_QUERIES:
                query_text = q_cfg["text"]
                top_k = q_cfg.get("top_k", 5)  # [Fix] 支持自定义 top_k，默认 5
                print(f"\n    Processing Query: [{query_text}]")

                # 执行检索 (Top 5)
                results = ProjectRAGService.search(self.project_id, query_text, top_k=top_k)

                # 格式化为 Prompt 所需的 Context 格式
                context_lines = []
                for res in results:
                    # 模拟 VSS Cloud 的 Context 组装格式
                    header = f"--- Source Scene [ID: {res['scene_local_id']}] (Relevance: {res['score']:.2f}) ---"  # noqa: E231,E501
                    body = res["raw_text"]
                    context_lines.append(f"{header}\n{body}\n")

                full_rag_context = "\n".join(context_lines)

                # 导出到文件
                filename = f"step_2b_context_{q_cfg['name']}.txt"
                output_file = OUTPUT_DIR / filename

                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(f"Query: {query_text}\n")
                    f.write(f"Narrative Focus: {q_cfg['narrative_focus']}\n")
                    f.write("=" * 80 + "\n")
                    f.write("RAG CONTEXT (Paste this into the prompt):\n")
                    f.write("=" * 80 + "\n\n")
                    f.write(full_rag_context)

                print(f"    [Artifact] RAG Context saved to: {output_file}")

        print("\n>>> Workflow Complete.")
        print(f"请前往 {OUTPUT_DIR} 查看生成的文件，并进行 Step 2.c (Google AI Studio 测试)。")
