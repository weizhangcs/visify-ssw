class CharacterRoleFinalizerContextMixin:
    def _payload_character_role_finalizer(self, target):
        # 输入依赖于 Fusion 步骤产生的 fused_metadata
        # 这是一个包含 speaker (PERSON_XX) 和 fusion_score 的片段列表
        return {"fusion_data": target.fused_metadata, "lang": "zh"}  # 暂时硬编码，后续可从 target.language 获取

    def _handle_character_role_finalizer(self, target, result):
        # 保存最终定稿的剧本和角色映射表
        target.finalized_script_meta = result

    def _check_character_role_finalizer_ready(self, target):
        return bool(target.fused_metadata)

    def _check_character_role_finalizer_done(self, target):
        return bool(target.finalized_script_meta)
