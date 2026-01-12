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
    1. [Reduce] 收集 Asset 下所有 Material 的对白。
    2. [Process] 调用 Cloud LLM 进行全剧角色一致性推理。
    3. [Scatter] 将统一后的角色名和角色列表分发回各个 Material。
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

        # 2. 准备合并的对白数据 (Map)
        # 我们需要一种方式在推理后将对白映射回原来的 Material
        # 策略：构造一个巨大的列表，每个 Item 增加一个 _material_id 标记 (Cloud API 会忽略额外字段，但我们需要自己维护映射)
        # 由于 CharacterRefinerService 使用的是标准 SubtitleItem，我们这里手动拼接

        all_dialogues = []
        # 记录每个 Material 的对白在总列表中的索引范围，以便后续拆分
        # material_id -> (start_index, end_index)
        ranges = {}
        current_idx = 0

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

        for mat in materials:
            dialogues = mat.dialogues or []
            count = len(dialogues)

            # 修正 index，使其在全局唯一 (防止 LLM 混淆)
            # 实际上 CharacterRefinerService 内部主要看 content 和 context，index 用于回填
            # 我们这里保持原始 index，但在回填时小心处理

            # 为了简单，我们直接把所有 dialogues 拼起来
            # 并在内存中记录归属
            all_dialogues.extend(dialogues)

            ranges[mat.id] = (current_idx, current_idx + count)
            current_idx += count

        logger.info(f"GlobalCharacterRefiner: Merged {len(all_dialogues)} lines from {len(materials)} materials.")

        # 3. 调用 LLM (Process)
        # 复用 CharacterRefinerService 的逻辑，它能处理长列表 (内部会上传文件)
        client = CloudApiService()
        asset_meta = {
            "video_title": video_title,
            "known_characters": known_characters,
            "lang": lang,
        }

        # 注意：如果对白非常多 (如 80集 * 300句 = 24000句)，单次 LLM 请求可能会超限或超时。
        # 理想情况下 Cloud 端支持分块处理。这里假设 Cloud 端能处理，或者我们在 Service 内部做分块。
        # 鉴于 CharacterRefinerService 是上传文件，文件大小通常不是问题，Cloud 端的 Context Window 是瓶颈。
        # VSS Cloud 应该有处理长文本的能力 (如 Map-Reduce 或 Sliding Window)。
        # 这里直接调用。
        result_data = CharacterRefinerService.run(client, all_dialogues, asset_meta)

        updates = result_data.get("identified_subtitles", [])
        # updates 是一个列表，包含 {index: ..., speaker: ..., reasoning: ...}
        # 问题：updates 里的 index 是原始 index。如果有多个 Material 都有 index=1，怎么区分？
        # CharacterRefinerService 并没有修改 index。
        # [Critical Fix]: 上面的合并策略有问题。如果多个集都有 index=1，LLM 返回 index=1 时我们不知道是哪一集的。
        # 解决方案：在合并前，重写 index 为全局唯一自增 ID。

        # --- 重来：构建全局唯一索引的对白列表 ---
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

        # 再次调用
        result_data = CharacterRefinerService.run(client, global_dialogues, asset_meta)
        updates = result_data.get("identified_subtitles", [])

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
