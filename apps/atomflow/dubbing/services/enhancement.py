import logging
import os

import torch
import torchaudio
from df.enhance import enhance, init_df, load_audio, save_audio

from apps.atomflow.dubbing import constants, utils

logger = logging.getLogger(__name__)


class AudioEnhancementService:
    """
    [物理算子] 人声增强服务
    """

    @staticmethod
    def run(vocals_path: str, mask_path: str, output_path: str) -> str:
        logger.info(f"Enhancement: Processing {os.path.basename(vocals_path)}...")

        # 1. 应用 Mask (Pre-processing)
        masks = torch.load(mask_path)
        vocals_wav, sr = torchaudio.load(vocals_path)

        mask = masks["perception"]
        if mask.dim() == 1:
            mask = mask.view(1, 1, -1)
        mask = torch.nn.functional.interpolate(mask, size=vocals_wav.shape[1], mode="nearest").squeeze(0)
        if vocals_wav.shape[0] > 1:
            mask = mask.expand(vocals_wav.shape[0], -1)

        # 生成中间文件
        pre_enhanced_path = output_path.replace(".wav", "_pre.wav")
        torchaudio.save(pre_enhanced_path, vocals_wav * mask, sr)

        # 2. DeepFilterNet 降噪
        enhancer = SignalEnhancerHelper(model_base_dir=constants.DEEPFILTERNET_MODEL_DIR)
        enhancer.run(pre_enhanced_path, output_path, atten_lim_db=30)
        logger.info(f"Enhancement completed. Output saved to {output_path}")

        del enhancer
        utils.cleanup_gpu()

        return output_path


class SignalEnhancerHelper:
    def __init__(self, model_base_dir):
        model_dir = os.path.join(model_base_dir, "DeepFilterNet3")
        # log_file=None 避免权限错误
        self.model, self.df_state, _ = init_df(model_base_dir=model_dir, log_file=None)

    def run(self, input_path, output_path, atten_lim_db=None):
        audio, _ = load_audio(input_path, sr=self.df_state.sr())
        enhanced = enhance(self.model, self.df_state, audio, atten_lim_db=atten_lim_db)
        save_audio(output_path, enhanced, self.df_state.sr())
        return output_path
