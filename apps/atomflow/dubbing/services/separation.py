import logging
import os
from pathlib import Path
from typing import Tuple

from audio_separator.separator import Separator

from apps.atomflow.dubbing import constants, utils

logger = logging.getLogger(__name__)


class AudioSeparationService:
    """
    [物理算子] 人声分离服务
    """

    @staticmethod
    def run(input_path: Path, output_dir: Path) -> Tuple[str, str]:
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Separation: Processing {input_path.name}...")

        # 使用 Audio-Separator 库
        separator = Separator(
            log_level=logging.WARNING,
            model_file_dir=constants.AUDIO_SEPARATOR_MODEL_DIR,
            output_dir=str(output_dir),
            output_single_stem=None,
        )

        model_filename = "model_bs_roformer_ep_317_sdr_12.9755.ckpt"
        separator.load_model(model_filename=model_filename)
        output_files = separator.separate(str(input_path))

        utils.cleanup_gpu()

        # 解析输出文件
        vocals = next((str(output_dir / f) for f in output_files if "Vocals" in f), None)
        inst = next((str(output_dir / f) for f in output_files if "Instrumental" in f or "Other" in f), None)

        if not vocals or not inst:
            logger.error(f"Separation failed for {input_path.name}. Output files detected: {output_files}")
            raise RuntimeError("Separation failed to produce Vocals and Instrumental stems.")

        logger.info(f"Separation completed: Vocals={os.path.basename(vocals)}, Inst={os.path.basename(inst)}")
        return vocals, inst
