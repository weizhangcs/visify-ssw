# 导入所需的标准库和第三方库
import csv
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import numpy as np
import onnxruntime as ort
import torch

# 导入项目内部模块
from apps.atomflow.dubbing import constants, utils

# 初始化日志记录器
logger = logging.getLogger(__name__)


# 定义配置类，用于存储语义门控的相关参数
@dataclass
class GatingConfig:
    """Configuration for the SemanticGatingHelper."""

    # YAMNet 语义过滤阈值
    yamnet_music_rejection_threshold: float = 0.30  # 音乐拒绝阈值
    yamnet_speech_keep_threshold: float = 0.10  # 语音保留阈值

    # VAD 感知掩码的严格阈值
    perception_vad_threshold: float = 0.20
    perception_min_speech_duration_ms: int = 150  # 最小语音持续时间（毫秒）
    perception_min_silence_duration_ms: int = 200  # 最小静音持续时间（毫秒）

    # VAD 材料掩码的宽松阈值
    material_vad_threshold: float = 0.15
    material_min_speech_duration_ms: int = 100  # 最小语音持续时间（毫秒）
    material_min_silence_duration_ms: int = 100  # 最小静音持续时间（毫秒）

    # 形态学操作的卷积核大小（以采样点为单位）
    yamnet_dilation_kernel: int = 8001  # YAMNet 膨胀卷积核
    perception_dilation_kernel: int = 4801  # 感知掩码膨胀卷积核
    material_dilation_kernel: int = 16001  # 材料掩码膨胀卷积核

    # 平滑卷积核大小（以毫秒为单位）
    perception_smooth_ms: int = 5  # 感知掩码平滑窗口
    material_smooth_ms: int = 50  # 材料掩码平滑窗口


# 主要的服务类，负责执行音频语义门控逻辑
class AudioGatingService:
    """
    [物理算子] 语义门控服务
    """

    @staticmethod
    def run(vocals_path: str, output_base: Path, config: GatingConfig = None) -> Dict:
        """
        执行语义门控分析并保存结果。

        参数:
            vocals_path (str): 输入人声文件路径。
            output_base (Path): 输出基础目录路径。
            config (GatingConfig): 可选的配置对象，默认使用默认配置。

        返回:
            Dict: 包含掩码文件路径和日志信息的结果字典。
        """
        logger.info(f"Gating: Analyzing {os.path.basename(vocals_path)}...")

        gater = None
        try:
            # 初始化语义门控助手
            gater = SemanticGatingHelper(
                model_path=constants.YAMNET_MODEL_PATH,
                class_map_path=constants.YAMNET_CLASS_MAP_PATH,
                vad_model_path=constants.VAD_MODEL_PATH,
                config=config,
            )
            # 处理音频并生成掩码
            masks, logs = gater.process(vocals_path)

            # 将掩码序列化并保存到磁盘
            mask_path = output_base / "gating_masks.pt"
            torch.save(masks, mask_path)
            logger.info(f"Gating completed. Masks saved to {mask_path}")

            return {"mask_path": str(mask_path), "logs": logs}
        finally:
            # 清理资源
            if gater:
                del gater
            utils.cleanup_gpu()


# 实现具体语义门控逻辑的核心类
class SemanticGatingHelper:
    def __init__(self, model_path, class_map_path, vad_model_path, config: GatingConfig = None, device="cuda"):
        """
        初始化语义门控助手。

        参数:
            model_path (str): YAMNet 模型路径。
            class_map_path (str): 类别映射文件路径。
            vad_model_path (str): VAD 模型路径。
            config (GatingConfig): 配置对象。
            device (str): 运行设备（默认为 CUDA）。
        """
        self.config = config or GatingConfig()
        self.sess = ort.InferenceSession(model_path, providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
        logger.info(f"YAMNet active providers: {self.sess.get_providers()}")
        self.input_name = self.sess.get_inputs()[0].name
        self.class_names = self._load_class_map(class_map_path)
        self.sr = 16000  # 采样率
        self.device = device

        # 定义需要保留和拒绝的类别
        self.keep_categories = {
            "Speech",
            "Child speech, kid speaking",
            "Conversation",
            "Narration, monologue",
            "Babbling",
            "Speech synthesizer",
            "Whispering",
        }
        self.reject_categories = {"Music", "Singing", "Humming", "Whistling", "Choir", "Yodeling", "Rapping", "Opera"}

        # 获取保留和拒绝类别的索引
        self.keep_indices = [i for i, name in enumerate(self.class_names) if name in self.keep_categories]
        self.reject_indices = [i for i, name in enumerate(self.class_names) if name in self.reject_categories]

        # 加载 VAD 模型
        self.vad_sess = ort.InferenceSession(
            vad_model_path, providers=["CUDAExecutionProvider", "CPUExecutionProvider"]
        )
        logger.info(f"VAD active providers: {self.vad_sess.get_providers()}")

    def _load_class_map(self, path):
        """
        加载类别映射文件。

        参数:
            path (str): 类别映射文件路径。

        返回:
            list: 类别名称列表。
        """
        names = []
        with open(path, "r") as f:
            reader = csv.reader(f)
            next(reader)  # 跳过标题行
            for row in reader:
                names.append(row[2])
        return names

    def process(self, audio_path):
        """
        对音频文件进行处理，生成感知掩码和材料掩码。

        参数:
            audio_path (str): 音频文件路径。

        返回:
            tuple: 掩码字典和日志列表。
        """
        t0 = time.time()
        wav = utils.load_audio_ffmpeg(audio_path, sr=self.sr)
        logger.info(f"Audio loaded & resampled with ffmpeg in {time.time() - t0:.3f}s")  # noqa: E231

        # 归一化音频信号
        max_val = np.max(np.abs(wav))
        if max_val > 0:
            wav = wav / max_val

        # 使用 YAMNet 模型推理
        inputs = {self.input_name: wav.astype(np.float32)}
        scores, _, _ = self.sess.run(None, inputs)

        # 生成感知掩码和材料掩码
        mask_perception, yamnet_dilated, logs = self._get_perception_mask(wav, scores)
        mask_material = self._get_material_mask(wav, scores)

        return {
            "yamnet_dilated": yamnet_dilated.cpu(),
            "perception": mask_perception.cpu(),
            "material": mask_material.cpu(),
        }, logs

    def _get_perception_mask(self, wav, scores):
        """
        生成感知掩码。

        参数:
            wav (np.ndarray): 音频波形数据。
            scores (np.ndarray): YAMNet 分类得分。

        返回:
            tuple: 感知掩码张量、YAMNet 膨胀掩码张量和日志列表。
        """
        frame_step = int(0.48 * self.sr)
        yamnet_mask_vec = np.zeros_like(wav)
        yamnet_music_vec = np.zeros_like(wav)
        logs = []

        # 遍历每个帧的分类得分
        for i, frame_scores in enumerate(scores):
            top_class_idx = np.argmax(frame_scores)
            top_class = self.class_names[top_class_idx]
            is_kept = top_class in self.keep_categories

            speech_scores = frame_scores[self.keep_indices]
            max_speech_score = float(np.max(speech_scores)) if len(speech_scores) > 0 else 0.0
            music_scores = frame_scores[self.reject_indices]
            max_music_score = float(np.max(music_scores)) if len(music_scores) > 0 else 0.0

            # 判断是否保留当前帧
            is_music = max_music_score > self.config.yamnet_music_rejection_threshold
            if not is_kept and max_speech_score > self.config.yamnet_speech_keep_threshold:
                is_kept = True
                is_music = False
            if is_kept and max_music_score > self.config.yamnet_music_rejection_threshold:
                is_kept = False
                is_music = True

            start_sample = i * frame_step
            end_sample = min(start_sample + int(0.96 * self.sr), len(wav))
            if is_kept:
                yamnet_mask_vec[start_sample:end_sample] = 1.0
            if is_music:
                yamnet_music_vec[start_sample:end_sample] = 1.0

        # 对 YAMNet 掩码进行膨胀操作
        dilation_kernel = self.config.yamnet_dilation_kernel
        yamnet_mask_tensor = torch.from_numpy(yamnet_mask_vec).float().view(1, 1, -1).to(self.device)
        yamnet_mask_tensor = torch.nn.functional.max_pool1d(
            yamnet_mask_tensor, kernel_size=dilation_kernel, stride=1, padding=dilation_kernel // 2
        )[..., : len(wav)]

        yamnet_music_tensor = torch.from_numpy(yamnet_music_vec).float().view(1, 1, -1).to(self.device)
        yamnet_music_tensor = torch.nn.functional.max_pool1d(
            yamnet_music_tensor, kernel_size=dilation_kernel, stride=1, padding=dilation_kernel // 2
        )[..., : len(wav)]

        # 生成 VAD 感知掩码
        vad_mask_perception_vec = self._run_vad(
            wav,
            threshold=self.config.perception_vad_threshold,
            min_speech_duration_ms=self.config.perception_min_speech_duration_ms,
            min_silence_duration_ms=self.config.perception_min_silence_duration_ms,
        )
        vad_mask_perception = torch.from_numpy(vad_mask_perception_vec).float().view(1, 1, -1).to(self.device)

        perception_dilation_kernel = self.config.perception_dilation_kernel
        vad_mask_perception = torch.nn.functional.max_pool1d(
            vad_mask_perception,
            kernel_size=perception_dilation_kernel,
            stride=1,
            padding=perception_dilation_kernel // 2,
        )[..., : len(wav)].squeeze()

        # 结合 VAD 和 YAMNet 音乐掩码生成最终感知掩码
        mask_perception = vad_mask_perception * (1.0 - yamnet_music_tensor.squeeze())
        mask_perception = self._smooth_mask(mask_perception, smooth_ms=self.config.perception_smooth_ms)

        return mask_perception, yamnet_mask_tensor.squeeze(), logs

    def _get_material_mask(self, wav, scores):
        """
        生成材料掩码。

        参数:
            wav (np.ndarray): 音频波形数据。
            scores (np.ndarray): YAMNet 分类得分。

        返回:
            torch.Tensor: 材料掩码张量。
        """
        # 生成 VAD 材料掩码
        vad_mask_material_vec = self._run_vad(
            wav,
            threshold=self.config.material_vad_threshold,
            min_speech_duration_ms=self.config.material_min_speech_duration_ms,
            min_silence_duration_ms=self.config.material_min_silence_duration_ms,
        )
        vad_mask_material = torch.from_numpy(vad_mask_material_vec).float().view(1, 1, -1).to(self.device)

        material_dilation_kernel = self.config.material_dilation_kernel
        vad_mask_material = torch.nn.functional.max_pool1d(
            vad_mask_material, kernel_size=material_dilation_kernel, stride=1, padding=material_dilation_kernel // 2
        )
        vad_mask_material = vad_mask_material[..., : len(wav)].squeeze()

        # 对掩码进行反向和平滑处理
        return 1.0 - self._smooth_mask(vad_mask_material, smooth_ms=self.config.material_smooth_ms)

    def _smooth_mask(self, mask_tensor, smooth_ms):
        """
        对掩码进行平滑处理。

        参数:
            mask_tensor (torch.Tensor): 输入掩码张量。
            smooth_ms (int): 平滑窗口大小（毫秒）。

        返回:
            torch.Tensor: 平滑后的掩码张量。
        """
        if smooth_ms <= 0:
            return mask_tensor
        kernel_size = int(smooth_ms * self.sr / 1000)
        if kernel_size % 2 == 0:
            kernel_size += 1
        padding = (kernel_size - 1) // 2

        if mask_tensor.dim() == 1:
            m = mask_tensor.view(1, 1, -1)
        elif mask_tensor.dim() == 2:
            m = mask_tensor.unsqueeze(1)
        else:
            m = mask_tensor

        smoothed = torch.nn.functional.avg_pool1d(m, kernel_size=kernel_size, stride=1, padding=padding)
        return smoothed.view(mask_tensor.shape)

    def _run_vad(self, wav, threshold=0.35, min_speech_duration_ms=250, min_silence_duration_ms=100):
        """
        运行语音活动检测（VAD）算法。

        参数:
            wav (np.ndarray): 音频波形数据。
            threshold (float): VAD 触发阈值。
            min_speech_duration_ms (int): 最小语音持续时间（毫秒）。
            min_silence_duration_ms (int): 最小静音持续时间（毫秒）。

        返回:
            np.ndarray: VAD 掩码数组。
        """
        window_size_samples = 512
        sr = 16000
        wav = wav.flatten().astype(np.float32)
        if len(wav) == 0:
            return np.zeros(0, dtype=np.float32)

        h = np.zeros((2, 1, 64), dtype=np.float32)
        c = np.zeros((2, 1, 64), dtype=np.float32)
        original_len = len(wav)

        # 填充音频长度使其能被窗口整除
        remainder = len(wav) % window_size_samples
        if remainder != 0:
            wav = np.pad(wav, (0, window_size_samples - remainder), mode="constant")

        vad_mask = np.zeros_like(wav)
        triggered = False
        temp_end = 0
        current_speech_start = 0
        min_speech_samples = int(min_speech_duration_ms * sr / 1000)
        min_silence_samples = int(min_silence_duration_ms * sr / 1000)

        # 遍历音频块进行 VAD 推理
        for i in range(0, len(wav), window_size_samples):
            chunk = wav[i : i + window_size_samples]
            if len(chunk) != window_size_samples:
                continue

            ort_inputs = {"input": chunk[np.newaxis, :], "sr": np.array([sr], dtype=np.int64), "h": h, "c": c}
            out, h, c = self.vad_sess.run(None, ort_inputs)
            prob = out[0][0]

            # 更新触发状态和掩码
            if prob >= threshold and temp_end:
                temp_end = 0
            if prob >= threshold and not triggered:
                triggered = True
                current_speech_start = i
                continue
            if triggered and prob < threshold:
                if temp_end == 0:
                    temp_end = i
                if (i - temp_end) >= min_silence_samples:
                    if (temp_end - current_speech_start) >= min_speech_samples:
                        vad_mask[current_speech_start:temp_end] = 1.0
                    triggered = False
                    temp_end = 0

        # 处理最后一段语音
        if triggered and (len(wav) - current_speech_start) >= min_speech_samples:
            vad_mask[current_speech_start:] = 1.0

        return vad_mask[:original_len]
