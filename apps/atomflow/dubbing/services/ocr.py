import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
import pandas as pd
import torch
from rapidocr_onnxruntime import RapidOCR

from apps.atomflow.dubbing import constants, utils

logger = logging.getLogger(__name__)


class OCRService:
    """
    [物理算子] OCR 分析服务
    [Strategy] High Recall for LLM (高召回模式)
    """

    @staticmethod
    def run(video_path: Path, output_dir: Path, mask_path: Optional[str] = None) -> Tuple[str, str]:
        logger.info(f"OCR: Analyzing {video_path.name}...")
        output_dir.mkdir(parents=True, exist_ok=True)

        analyzer = FastOCRHelper(model_dir=constants.OCR_DIR, mask_path=mask_path)
        # 返回两个路径：Inpainting用的索引 CSV，和 LLM 用的聚合 CSV
        ocr_index_path, llm_csv_path = analyzer.run(str(video_path), str(output_dir))

        del analyzer
        utils.cleanup_gpu()

        return ocr_index_path, llm_csv_path


class FastOCRHelper:
    def __init__(self, model_dir, mask_path=None):
        # 仅保留核心 OCR 引擎，开启 CUDA
        self.ocr = RapidOCR(
            det_model_path=os.path.join(model_dir, "ch_PP-OCRv4_det_infer.onnx"),
            rec_model_path=os.path.join(model_dir, "ch_PP-OCRv4_rec_infer.onnx"),
            # LLM 场景下 CLS 模型可以省略以加速，除非有大量旋转文字
            det_use_cuda=True,
            rec_use_cuda=True,
        )
        self.last_hash = None
        self.last_result = None
        self.sample_step = 1  # [Fix] 改为逐帧处理，确保 Inpainting 掩码的连续性和准确性

        # 加载 Gating Mask (如果提供)
        self.speech_mask = None
        if mask_path and os.path.exists(mask_path):
            try:
                logger.info(f"   [OCR] Loading gating mask from {mask_path}...")
                masks = torch.load(mask_path, map_location="cpu")
                if "perception" in masks:
                    self.speech_mask = masks["perception"].float().numpy().flatten()
                    self.sr = 16000  # Gating 固定采样率
            except Exception as e:
                logger.warning(f"   [OCR] Failed to load mask: {e}")

    def _get_frame_hash(self, img):
        """极速计算画面指纹 (亮度均值)，用于判断画面是否静止"""
        # 缩放到 32x32 极小图计算
        small = cv2.resize(img, (32, 32), interpolation=cv2.INTER_NEAREST)
        return cv2.mean(small)[0]

    def run(self, video_path, output_dir):
        cap = utils.FFmpegVideoReader(video_path)
        fps = cap.fps
        total_frames = cap.total_frames
        h, w = cap.height, cap.width

        # 策略 1：锁定下半部 50% (LLM 场景下，我们假设关键信息/字幕多在下方)
        # 如果需要全屏 OCR，可改为 ry1=0
        ry1, ry2 = int(h * 0.5), h

        raw_ocr_data = []
        frame_idx = 0

        logger.info(f"   [OCR] Starting Fast OCR (Step={self.sample_step})...")
        start_time = time.time()

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # 策略 2：物理跳帧 (FFmpegReader 是管道流，只能读不能 Seek，所以通过取模跳过处理)
            if frame_idx % self.sample_step != 0:
                frame_idx += 1
                continue

            # [Optimization] 策略 2.5: 语义门控过滤 (如果提供了 Audio Mask)
            if self.speech_mask is not None:
                # 映射到音频采样点 (假设 16kHz)
                sample_idx = int((frame_idx / fps) * self.sr)
                # 宽松边界检查
                if 0 <= sample_idx < len(self.speech_mask):
                    # 阈值判定：如果当前时刻人声概率极低 (<0.1)，则跳过 OCR
                    if self.speech_mask[sample_idx] < 0.1:
                        frame_idx += 1
                        continue

            roi_frame = frame[ry1:ry2, :]

            # 策略 3：视觉指纹校验 (如果画面没变，复用上一次结果，极大节省推理时间)
            # [Fix] 禁用哈希校验。简单的亮度均值哈希无法检测画面平移/字幕滚动，会导致掩码位置滞后。
            # 为了去字幕效果，必须逐帧重新检测。
            # curr_hash = self._get_frame_hash(roi_frame)
            # if self.last_hash and abs(curr_hash - self.last_hash) < 1.0:
            #     ocr_result = self.last_result
            # else:

            # 策略 4：暴力识别，不做预处理 (RapidOCR 内部已有 Resize/Normalize)
            ocr_result, _ = self.ocr(roi_frame)
            # self.last_hash = curr_hash
            # self.last_result = ocr_result

            # 策略 5：召回优先，仅过滤极低置信度的纯乱码
            if ocr_result:
                for item in ocr_result:
                    box, text, score = item[0], item[1], item[2]
                    if score > 0.4:  # 极低门槛，保留尽可能多的信息给 LLM
                        # 坐标还原 (相对于全图)
                        box_np = np.array(box)
                        box_np[:, 1] += ry1

                        raw_ocr_data.append(
                            {
                                "frame_idx": frame_idx,
                                "time": round(frame_idx / fps, 3),
                                "text": text,
                                "score": round(float(score), 2),
                                "boxes": box_np.tolist(),  # 保留 Box 供 Inpainting 使用
                            }
                        )

            frame_idx += 1
            if frame_idx % 100 == 0:
                current_time = time.time() - start_time
                logger.info(
                    f"   [OCR] Progress: {frame_idx}/{total_frames} frames processed (Time: {current_time:.2f}s)"  # noqa: E231,E501
                )
                sys.stdout.flush()

        cap.release()

        # 导出结果
        return self._export_data(output_dir, raw_ocr_data, h, w)

    def _is_valid_for_inpainting(self, item, h_frame, w_frame):
        """
        [Inpainting Track] 严格过滤逻辑
        只保留确信是字幕的内容，防止误擦除背景物体。
        """
        box = np.array(item["boxes"])
        score = item["score"]
        text = item["text"]

        # 1. 几何约束 (Aspect Ratio)
        # 字幕通常是扁长的。排除竖长或正方(1:1)的物体(如Logo、图标)
        x_min, x_max = np.min(box[:, 0]), np.max(box[:, 0])
        y_min, y_max = np.min(box[:, 1]), np.max(box[:, 1])
        w = x_max - x_min
        h = y_max - y_min

        if h <= 0:
            return False
        # 长宽比 < 1.2 (接近正方形或竖长) 予以拒绝
        if (w / h) < 1.2:
            return False

        # 2. 位置约束 (Static Anchor)
        # 假设短剧字幕主要在底部 30% (0.7h - 1.0h)
        # 如果中心点在 0.7h 以上，除非置信度极高，否则认为是背景文字
        y_center = (y_min + y_max) / 2
        is_in_subtitle_zone = y_center > (h_frame * 0.65)  # 稍微放宽到 0.65

        if not is_in_subtitle_zone:
            return False

        # 3. 语义约束 (Confidence-Density)
        # 高置信度直接放行；中置信度需配合字数长度
        if score > 0.85:
            return True
        elif score > 0.5 and len(text) > 3:
            return True

        return False

    def _export_data(self, output_dir, data, h_frame, w_frame):
        if not data:
            return None, None

        df = pd.DataFrame(data)

        # --- Track 1: Inpainting (Strict Filtering & Aggregation) ---
        # 必须按 frame_idx 聚合，否则同一帧的多行字幕会互相覆盖
        inpainting_map = {}
        for item in data:
            if self._is_valid_for_inpainting(item, h_frame, w_frame):
                fid = item["frame_idx"]
                if fid not in inpainting_map:
                    inpainting_map[fid] = []
                inpainting_map[fid].append(item["boxes"])

        inpainting_rows = []
        for fid, boxes_list in inpainting_map.items():
            inpainting_rows.append({"frame_idx": fid, "boxes": json.dumps(boxes_list)})  # 序列化为 [[x,y]...], [[x,y]...]

        df_inpainting = pd.DataFrame(inpainting_rows)
        ocr_index_path = os.path.join(output_dir, "ocr_index.csv")
        df_inpainting.to_csv(ocr_index_path, index=False)

        # --- Track 2: LLM (High Recall & Rough Aggregation) ---
        # 使用原始数据，保留低置信度文本，由 LLM 自行甄别
        # 简单的去重合并逻辑：相同文字在连续时间段内出现则合并
        # 这里的 group 逻辑：如果当前行 text 与上一行不同，则 group_id + 1
        df["group"] = (df["text"] != df["text"].shift()).cumsum()

        llm_df = df.groupby(["group", "text"]).agg({"time": ["min", "max"], "score": "mean"}).reset_index()

        # 展平列名
        llm_df.columns = ["group", "text", "start_time", "end_time", "avg_score"]
        llm_df = llm_df[["start_time", "end_time", "text", "avg_score"]]

        llm_csv_path = os.path.join(output_dir, "ocr_raw_for_llm.csv")
        llm_df.to_csv(llm_csv_path, index=False)

        return ocr_index_path, llm_csv_path
