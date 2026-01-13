# apps/atomflow/refinery/services/global_character_refiner.py
import logging
from typing import List

from apps.atomflow.refinery.models import Material
from apps.atomflow.refinery.schemas import IdentifiedCharacterItem, RoleType, RoleTypeLabel
from apps.atomflow.refinery.services.character_refiner import CharacterRefinerService
from apps.common.cloud_client import CloudApiService

logger = logging.getLogger(__name__)


class GlobalCharacterRefinerService:
    """
    [Refinery Asset Operator] 全局角色统筹服务 (Map-Reduce)。

    职责：
    1. [Reduce - 聚合] 收集 Asset 下所有 Material 的对白数据。
    2. [Process - 推理] 调用 Cloud REFINERY_CHARACTER_IDENTIFIER 接口进行全剧角色一致性推理。
       - 注意：Cloud 端具备 Batch Inference 能力，会自动处理超长文本的分块，Edge 端无需手动切分。
    3. [Scatter - 分发] 将统一后的角色名和角色列表分发回各个 Material。

    架构特性说明：
    - **全局索引重构 (Global Indexing)**: 本服务是 Refinery 中唯一需要构建跨 Material 全局索引的算子。
      它将多个集的局部索引 (Local Index) 映射为全局唯一自增 ID，以确保 Cloud 端推理上下文的连贯性，
      并支持结果的精确回填。因此，它不需要在 Context 层进行额外的排序后处理。
    """

    @staticmethod
    def run(asset_id: str, pipeline_ids: List[str]) -> None:
        """
        执行全局角色精修。

        Args:
            asset_id: 资产 ID。
            pipeline_ids: 涉及的 Pipeline ID 列表。
        """
        # 1. 加载所有 Materials
        # 通过 pipeline_ids 反查 Material，确保顺序 (通常按集数)
        materials = (
            Material.objects.filter(pipeline__id__in=pipeline_ids)
            .select_related("media", "media__asset")
            .order_by("media__sequence_number")
        )

        if not materials:
            logger.warning("GlobalCharacterRefiner: No materials found.")
            return

        # 获取 Asset 元数据 (取第一个 Material 的即可)
        first_mat = materials[0]
        asset = getattr(first_mat.media, "asset", None)
        lang = "zh"
        known_characters = []
        video_title = "Global Asset"

        if asset:
            if asset.language:
                lang = asset.language.split("-")[0]
            known_characters = asset.known_characters or []
            video_title = asset.title

        # 2. 构建全局唯一索引的对白列表 (Map & Re-index)
        # 目的：解决多集 Material 之间 Local Index 冲突的问题 (如每集都有 index=1)。
        # 策略：构建一个虚拟的全局时间轴，将所有对白按顺序赋予全局唯一自增 ID (gid)。
        #       同时维护 global_index_map 用于结果回填。
        global_dialogues = []
        global_index_map = {}  # global_index -> (material_id, local_index)

        gid = 0
        for mat in materials:
            for item in mat.dialogues:
                # 深拷贝
                new_item = item.copy()
                local_index = new_item.get("index")

                # 赋予全局唯一 index
                new_item["index"] = gid
                global_index_map[gid] = (mat.id, local_index)

                global_dialogues.append(new_item)
                gid += 1

        logger.info(f"GlobalCharacterRefiner: Merged {len(global_dialogues)} lines from {len(materials)} materials.")

        # 3. 调用 Cloud API (Process)
        client = CloudApiService()
        asset_meta = {
            "video_title": video_title,
            "known_characters": known_characters,
            "lang": lang,
        }

        result_data = CharacterRefinerService.run(client, global_dialogues, asset_meta)
        updates = [item.model_dump() for item in result_data.identified_subtitles]

        # 4. 拆分结果并回填 (Scatter)
        # 准备数据容器
        material_updates = {mat.id: {} for mat in materials}  # mat_id -> {local_index: update_data}

        # 统计每个 Material 出现的角色
        material_characters = {mat.id: set() for mat in materials}  # mat_id -> {character_name}

        for update in updates:
            g_idx = update.get("index")
            if g_idx in global_index_map:
                mat_id, local_idx = global_index_map[g_idx]

                # 记录更新
                material_updates[mat_id][local_idx] = update

                # 记录角色
                speaker = update.get("speaker")
                if speaker and speaker not in ["Unknown", "Others"]:
                    material_characters[mat_id].add(speaker)

        # 5. 持久化
        for mat in materials:
            # A. 更新 Dialogues
            updates_map = material_updates.get(mat.id, {})
            if updates_map:
                new_dialogues = []
                for item in mat.dialogues:
                    idx = item.get("index")
                    if idx in updates_map:
                        u = updates_map[idx]
                        if "speaker" in u:
                            item["speaker"] = u["speaker"]
                        if "reasoning" in u:
                            item["reasoning"] = u["reasoning"]
                    new_dialogues.append(item)
                mat.dialogues = new_dialogues

            # B. 更新 Identified Characters
            # 根据本集出现的角色，生成 IdentifiedCharacterItem 列表
            # 这里做一个简单的推断：role_type 默认为 Unknown，需要后续人工或更高级的分析
            # 或者我们可以统计出现频次来推断 Main/Supporting
            chars_in_episode = material_characters.get(mat.id, set())
            char_items = []

            # 简单的频次统计 (可选优化)
            # speaker_counts = Counter([d['speaker'] for d in mat.dialogues])

            for name in sorted(list(chars_in_episode)):
                # 尝试从 known_characters 匹配更多信息
                # known_char = next((k for k in known_characters if k['name'] == name), None)

                char_item = IdentifiedCharacterItem(
                    name=name,
                    role_type=RoleTypeLabel(value=RoleType.UNKNOWN, label="未知"),  # 使用枚举成员
                    description=None,
                )
                char_items.append(char_item.model_dump())

            mat.identified_characters = char_items
            mat.save()

        logger.info("GlobalCharacterRefiner: Scatter complete.")
