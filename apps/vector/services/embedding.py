import logging
from pathlib import Path
from typing import List, Union

import numpy as np

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None


class EmbeddingService:
    """
    [Infrastructure] 向量化服务
    封装 SentenceTransformer，提供文本转向量能力。
    """

    # [Upgrade] 升级为 E5-Large 多语言模型
    # 理由: Edge 设备算力充足且流程异步，优先追求语义质量。
    # 维度: 384 -> 1024
    # 提示: 检索(Query)时建议添加 "query: " 前缀，构建索引(Passage)时无需前缀。
    MODEL_NAME = "intfloat/multilingual-e5-large"
    _model_instance = None

    @classmethod
    def get_model(cls):
        """单例模式加载模型"""
        if cls._model_instance is None:
            if SentenceTransformer is None:
                raise RuntimeError("缺少 sentence-transformers 依赖")

            # 路径检查优先级:
            # 1. Docker 容器内路径 (/app/local_models)
            # 2. 本地开发环境路径 (项目根目录/local_models)
            # 3. 在线下载 (HuggingFace Hub)

            docker_path = Path("/app/local_models") / cls.MODEL_NAME
            local_dev_path = Path(__file__).resolve().parent.parent.parent.parent / "local_models" / cls.MODEL_NAME

            if docker_path.exists():
                model_path = str(docker_path)
            elif local_dev_path.exists():
                model_path = str(local_dev_path)
            else:
                logger.warning(f"Offline model not found locally. Downloading from HF Hub: {cls.MODEL_NAME}")
                model_path = cls.MODEL_NAME

            logger.info(f"Loading Embedding Model from: {model_path}")
            # [Fix] 传递 tokenizer_kwargs 以修复 Mistral regex warning
            cls._model_instance = SentenceTransformer(model_path, tokenizer_kwargs={"fix_mistral_regex": True})
        return cls._model_instance

    @classmethod
    def encode(cls, texts: Union[str, List[str]]) -> np.ndarray:
        """
        生成文本向量。
        """
        model = cls.get_model()
        # show_progress_bar=False 避免日志刷屏
        embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)

        # 归一化以支持余弦相似度 (FAISS Inner Product)
        if len(embeddings.shape) == 1:
            norm = np.linalg.norm(embeddings)
            if norm > 0:
                embeddings = embeddings / norm
        else:
            # 批量归一化
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            embeddings = embeddings / (norms + 1e-10)  # 防止除零

        return embeddings
