import argparse
import logging
import sys
from pathlib import Path

# 尝试导入依赖
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    print("Error: 'sentence-transformers' library is not installed.")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def download(model_name: str, output_dir: str):
    """
    下载模型并保存到指定目录
    """
    # 计算绝对路径
    path_obj = Path(output_dir)
    if not path_obj.is_absolute():
        # 脚本位于 scripts/build/，向上 3 级是项目根目录
        project_root = Path(__file__).resolve().parent.parent.parent
        target_dir = project_root / output_dir
    else:
        target_dir = path_obj

    full_model_path = target_dir / model_name

    logger.info("----------------------------------------------------------------")
    logger.info(f"Model:  {model_name}")  # noqa: E241
    logger.info(f"Target: {full_model_path}")
    logger.info("----------------------------------------------------------------")

    if full_model_path.exists():
        logger.warning(f"Directory {full_model_path} already exists. It will be overwritten/updated.")

    logger.info("Starting download from HuggingFace Hub...")
    try:
        model = SentenceTransformer(model_name)
        logger.info("Download complete. Saving to local disk...")
        model.save(str(full_model_path))
        logger.info(f"✅ Successfully saved to: {full_model_path}")
    except Exception as e:
        logger.error(f"❌ Failed to download model: {e}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VSS Edge Model Downloader")
    parser.add_argument("--model", type=str, required=True, help="HuggingFace model name")
    parser.add_argument("--output", type=str, default="local_models", help="Output directory relative to project root")

    args = parser.parse_args()
    download(args.model, args.output)
