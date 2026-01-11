from django.core.management.base import BaseCommand

from apps.inference.services.material_selector import MaterialSelectorService


class Command(BaseCommand):
    help = "测试本地 RAG 检索功能"

    def add_arguments(self, parser):
        parser.add_argument("material_id", type=str, help="已生成索引的 Material ID")
        parser.add_argument("query", type=str, help="测试查询语句")

    def handle(self, *args, **options):
        material_id = options["material_id"]
        query = options["query"]

        self.stdout.write("正在初始化选择器...")
        selector = MaterialSelectorService()

        self.stdout.write(f"正在检索 Material: {material_id}")
        self.stdout.write(f"Query: {query}")

        results = selector.search(material_id, query, top_k=3)

        if not results:
            self.stdout.write(self.style.WARNING("未找到匹配结果或索引不存在。"))
            return

        self.stdout.write(self.style.SUCCESS(f"\n成功召回 {len(results)} 个结果: \n"))

        for i, res in enumerate(results):
            self.stdout.write(f"--- Rank {i+1} (Score: {res['score']:.4f}) ---")  # noqa: E226,E231
            self.stdout.write(f"Slice ID: {res['slice_id']}")
            self.stdout.write(
                f"Time: {res['start_time']:.2f}s - {res['end_time']:.2f}s (Duration: {res['duration']:.2f}s)"  # noqa:E231,E501
            )

            # 尝试从 Material 中读取更多详情 (可选)
            # material = Material.objects.get(id=material_id)
            # slice_data = next((s for s in material.slices if s['slice_id'] == res['slice_id']), None)
            # if slice_data and slice_data.get('slice_analysis'):
            #     self.stdout.write(f"Visual: {slice_data['slice_analysis'].get('visual_summary')}")

            self.stdout.write("")
