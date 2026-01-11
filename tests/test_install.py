import faiss
from sentence_transformers import SentenceTransformer


def test_multilingual_rag():
    print("1. 正在加载多语言模型 (首次运行会自动下载约 470MB 模型文件)...")
    # 使用支持 50+ 种语言的模型
    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    print("   模型加载成功！")

    # 模拟 Refinery 的切片数据 (混合语言)
    slices_text = [
        "A man is running in the rain, looking anxious.",  # 英文描述
        "特写镜头，一个女孩在微笑，阳光明媚。",  # 中文描述
        "Two cars crashing on the highway.",  # 英文描述
        "黑暗的地下室，只有一盏昏暗的灯。",  # 中文描述
    ]

    print(f"\n2. 正在生成 {len(slices_text)} 条切片的向量...")
    # 生成向量 (Embeddings)
    embeddings = model.encode(slices_text)

    # 归一化 (为了让内积等价于余弦相似度)
    faiss.normalize_L2(embeddings)

    print(f"   向量维度: {embeddings.shape[1]}")

    # 构建 FAISS 索引
    d = embeddings.shape[1]
    index = faiss.IndexFlatIP(d)  # Inner Product (内积)
    index.add(embeddings)
    print(f"   FAISS 索引构建完成，包含 {index.ntotal} 条数据。")

    # --- 测试检索 ---
    # 使用中文 Query 搜索英文素材，测试跨语言能力
    query = "下雨天有人在奔跑"
    print(f"\n3. 执行跨语言检索测试: Query='{query}'")

    query_vec = model.encode([query])
    faiss.normalize_L2(query_vec)

    # 搜索 Top 1
    D, I = index.search(query_vec, 1)  # noqa: E741

    best_match_idx = I[0][0]
    score = D[0][0]
    best_match_text = slices_text[best_match_idx]

    print(f'   [结果] 匹配到的切片: "{best_match_text}"')
    print(f"   [分数] 相似度: {score:.4f}")  # noqa: E231

    if best_match_idx == 0:
        print("\n✅ 测试通过！成功匹配到了语义对应的英文切片。")
    else:
        print("\n❌ 测试未通过，匹配结果不符合预期。")


if __name__ == "__main__":
    test_multilingual_rag()
