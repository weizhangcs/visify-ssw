from pathlib import Path

from sentence_transformers import SentenceTransformer


def download_model_locally():
    model_name = "paraphrase-multilingual-MiniLM-L12-v2"
    # 定义保存路径：项目根目录/local_models/模型名
    output_path = Path(__file__).parent.parent / "local_models" / model_name

    print(f"正在下载模型 '{model_name}' 到: {output_path} ...")

    # 下载并保存
    model = SentenceTransformer(model_name)
    model.save(str(output_path))

    print("✅ 模型下载完成！")
    print("请确保 'local_models' 目录位于 Docker 构建上下文的根目录。")


if __name__ == "__main__":
    download_model_locally()
