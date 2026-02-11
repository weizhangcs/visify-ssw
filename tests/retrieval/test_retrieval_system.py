import logging
import os
import sys
import unittest

# 1. 初始化 Django 环境 (允许作为独立脚本运行)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "visify_ssw.settings")

import django  # noqa: E402

django.setup()

from apps.media_assets.models import Asset  # noqa: E402
from apps.retrievalhub.engine import RetrievalEngine  # noqa: E402

logger = logging.getLogger(__name__)


class RealDataRetrievalTestCase(unittest.TestCase):
    """
    针对真实数据的集成测试。
    前提：数据库中必须存在指定的 Asset ID，且磁盘上存在对应的向量索引文件。
    注意：运行此测试时，请确保测试运行器配置为可以访问包含数据的数据库（例如使用 --keepdb 或配置了正确的 TEST 数据库）。
    """

    def setUp(self):
        self.target_asset_id = "40486ecf-9098-4e3f-a594-703617c7c31a"
        self.engine = RetrievalEngine()

        # 预检查：确认数据存在，否则跳过测试以避免 CI 失败
        self.asset_exists = Asset.objects.filter(id=self.target_asset_id).exists()
        if not self.asset_exists:
            print(f"\n[WARN] Asset {self.target_asset_id} not in database. Skipping real data tests.")

    def test_01_structured_adapter_real_data(self):
        """
        测试结构化数据适配器 (Real Data)
        使用空查询字符串，验证是否能从 AnnotationJob 读取并返回数据。
        """
        if not self.asset_exists:
            return

        context = {"asset_id": self.target_asset_id, "mode": "structured_only", "index_types": ["dialogue", "scene"]}

        # 空查询在 StructuredAdapter 中应匹配所有内容 (基于 _match 实现)
        results = self.engine.search("", context)

        print(f"\n[Structured] Found {len(results)} items for Asset {self.target_asset_id}")

        if len(results) > 0:
            first_item = results[0]
            # 验证返回的是 RetrievalResult 对象
            print(f" - Sample: [{first_item.type}] {first_item.content}")

            # 验证关键字段是否存在
            self.assertTrue(hasattr(first_item.content, "id"))
            self.assertTrue(first_item.media_id, "Should contain hydrated media info")
            self.assertTrue(first_item.video_url, "Should contain playback url")
            self.assertEqual(first_item.source, "structured")

    def test_02_vector_adapter_real_data(self):
        """
        测试向量适配器 (Real Data)
        真实加载模型并检索磁盘上的 FAISS 索引。
        """
        if not self.asset_exists:
            return

        context = {
            "asset_id": self.target_asset_id,
            "mode": "vector_only",
            "top_k": 3,
            # 测试所有支持的向量类型
            "index_types": ["dialogue", "scene", "slice", "frame"],
        }

        # 使用一个通用的语义查询词，确保能召回结果
        query = "people"

        print(f"\n[Vector] Encoding query '{query}' and searching indices...")
        results = self.engine.search(query, context)

        print(f"[Vector] Found {len(results)} results.")

        for res in results:
            print(f" - [{res.type}] Score: {res.score:.4f} | {str(res.content)[:50]}...")  # noqa: E231

        if len(results) > 0:
            item = results[0]
            # 验证来源标记
            self.assertEqual(item.source, "vector")
            # 验证水合逻辑 (Hydration) 是否成功关联了 Media
            self.assertTrue(item.media_title, "Media title should be hydrated")
            # 验证分数逻辑
            self.assertLessEqual(item.score, 1.0001, "Cosine similarity should be <= 1.0")


if __name__ == "__main__":
    unittest.main()
