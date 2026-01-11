import logging
from typing import Any, Dict

from apps.atomflow.refinery.models import Material
from apps.inference.services.material_selector import MaterialSelectorService

# 假设您有一个封装好的 LLM Client，如果没有，这里可以用原生 google.generativeai
# from apps.common.llm_client import GeminiClient

logger = logging.getLogger(__name__)


class NarrationGeneratorService:
    """
    [Local Service] 本地解说词生成服务

    职责：
    1. 加载 Refinery 产出的向量索引 (Scene/Slice Index)。
    2. 根据 Orchestrator 传来的配置 (Config)，构建 Prompt。
    3. 执行 RAG 检索，获取上下文。
    4. 调用 LLM 生成解说词脚本。
    """

    def __init__(self, project):
        self.project = project
        self.asset = project.asset
        # 通过 Asset 反查 Material
        self.material = Material.objects.filter(media__asset=self.asset).first()

        if not self.material:
            raise ValueError(f"Asset {self.asset.id} 尚未经过 Refinery 处理，无 Material 数据")

        # 初始化 RAG 选择器
        self.selector = MaterialSelectorService()

    def execute(self, config: Dict[str, Any]) -> Dict:
        """
        执行生成逻辑
        :param config: 来自 Form 的扁平化配置 (narrative_focus, style, etc.)
        :return: 生成的脚本 JSON 结构
        """
        logger.info(f"开始本地生成解说词 Project: {self.project.id}")

        # 1. 准备上下文 (RAG)
        # 这里我们使用 Scene Index 来生成大纲/解说
        context_data = self._retrieve_context(config)

        # 2. 构建 Prompt
        prompt = self._build_prompt(config, context_data)

        # 3. 调用 LLM (模拟)
        # response = GeminiClient.generate(prompt)
        # 这里模拟一个返回结果，实际开发时替换为真实 LLM 调用
        logger.info(f"Sending Prompt to LLM: {prompt[:100]}...")

        # --- MOCK LLM RESPONSE ---
        generated_content = self._mock_llm_response(config)
        # -------------------------

        return generated_content

    def _retrieve_context(self, config: Dict) -> str:
        """
        利用 MaterialSelectorService 从本地索引中检索相关剧情
        """
        if not self.material.local_scene_index_path:
            logger.warning("未找到 Scene Index，将使用纯 LLM 生成 (无 RAG)")
            return "无详细剧情索引"

        query = config.get("custom_narrative_prompt") or config.get("narrative_focus", "general")
        top_k = config.get("rag_top_k", 5)

        # 调用 Inference 模块的能力
        # 注意：这里假设 selector 已经支持了 scene 维度的检索，或者我们复用 slice 检索
        candidates = self.selector.search(material_id=str(self.material.id), query=query, top_k=top_k)

        context_str = "\n".join(
            [f"- Scene {c.get('scene_index', '?')}: {c.get('narrative_summary', '')}" for c in candidates]
        )
        return context_str

    def _build_prompt(self, config: Dict, context: str) -> str:
        return f"""
        你是一个专业的电影解说文案创作者。
        
        【任务配置】
        焦点: {config.get('narrative_focus')} 
        风格: {config.get('style')}
        视角: {config.get('perspective')}
        
        【剧情上下文 (RAG检索结果)】
        {context}
        
        请生成一份 JSON 格式的解说词脚本。
        """

    def _mock_llm_response(self, config: Dict) -> Dict:
        """模拟返回结构，保持与云端契约一致"""
        return {
            "narration_script": [
                {
                    "time_code": "00:00:00",
                    "narration": f"这是一个基于本地 RAG 生成的测试解说。风格：{config.get('style')}。",
                    "visual_cue": "开场画面",
                },
                {"time_code": "00:00:10", "narration": "随着剧情的深入，我们可以看到主角的内心变化。", "visual_cue": "主角特写"},
            ]
        }
