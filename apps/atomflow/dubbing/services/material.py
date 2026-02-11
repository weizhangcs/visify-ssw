import logging
from pathlib import Path

import torch
import torchaudio

logger = logging.getLogger(__name__)


class MaterialBuilderService:
    """
    [物理算子] 素材轨构建服务
    """

    @staticmethod
    def run(inst_path: str, vocals_path: str, mask_path: str, enhanced_path: str, output_path: str) -> str:
        logger.info(f"Material: Composing M&E track for {Path(inst_path).name}...")

        masks = torch.load(mask_path)
        speech_mask = 1.0 - masks["material"]  # Invert logic

        # Load components
        inst, sr = torchaudio.load(inst_path)
        vocals, _ = torchaudio.load(vocals_path)
        enhanced, sr_enh = torchaudio.load(enhanced_path)
        device = vocals.device

        # Align Lengths
        min_len = min(inst.shape[1], vocals.shape[1])
        inst = inst[:, :min_len]
        vocals = vocals[:, :min_len]

        # Align Mask
        if speech_mask.dim() == 1:
            speech_mask = speech_mask.view(1, 1, -1)
        speech_mask = torch.nn.functional.interpolate(speech_mask, size=min_len, mode="nearest").squeeze(0)
        if vocals.shape[0] > 1:
            speech_mask = speech_mask.expand(vocals.shape[0], -1)

        # Calculate Components
        non_speech_part = vocals * (1.0 - speech_mask)

        # Align Enhanced
        if sr_enh != sr:
            resampler = torchaudio.transforms.Resample(sr_enh, sr).to(device)
            enhanced = resampler(enhanced)

        if enhanced.shape[1] < min_len:
            pad = torch.zeros(enhanced.shape[0], min_len - enhanced.shape[1]).to(device)
            enhanced = torch.cat([enhanced, pad], dim=1)
        else:
            enhanced = enhanced[:, :min_len]

        # residual_part = (vocals * speech_mask) - enhanced

        # material = inst + non_speech_part + residual_part
        # [说明] 暂时移除 residual_part 回填。测试发现残差中仍包含明显人声残留，破坏了背景轨纯净度。
        # 待将来引入更精细的残差提取算法（如去混响或相位抵消优化）后再恢复此部分。
        material = inst + non_speech_part

        torchaudio.save(output_path, material, sr)
        logger.info(f"Material construction completed. Saved to {output_path}")
        return output_path
