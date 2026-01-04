import logging
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np

from ..schemas import FrameDataInput

logger = logging.getLogger(__name__)


class FrameProbeService:
    """
    [分析算子] 帧质量探测服务 (L0 特征)。

    职责：
    1. 检查物理帧文件是否存在。
    2. 计算帧的模糊度 (Laplacian Variance)。
    3. 检测黑帧/白帧。
    4. 更新 FrameDataInput 中的 quality_score 和 filter_reason。
    """

    @staticmethod
    def run(keyframe_map: Dict[str, List[Dict]], media_root: Path) -> Dict[str, List[Dict]]:
        """
        执行帧探测任务。

        Args:
            keyframe_map: 关键帧映射表 (Slice ID -> FrameDataInput List)。
            media_root: 媒体文件根目录 (用于拼接绝对路径)。

        Returns:
            更新后的 keyframe_map。
        """
        logger.info(f"Frame Probe Start: {len(keyframe_map)} slices in keyframe_map to analyze.")

        # 内容缓存：基于 Digest 去重，避免对相同内容的图片重复计算
        # digest (or path) -> (quality_score, filter_reason)
        processed_cache = {}

        updated_keyframe_map = {}
        for slice_id, frames_list_dict in keyframe_map.items():
            updated_frames_for_slice = []
            for frame_data_dict in frames_list_dict:
                # 确保操作的是 FrameDataInput 实例，并进行深拷贝以避免修改原始对象
                frame = FrameDataInput(**frame_data_dict)
                abs_path = media_root / frame.path

                # 如果路径已经是云端路径 (gs:// 或 http://)，说明已同步，跳过本地探测
                if frame.path.startswith(("gs://", "http")):
                    updated_frames_for_slice.append(frame.model_dump())
                    continue

                # 严格使用 digest 作为唯一的缓存和去重键
                cache_key = frame.digest

                # 1. 检查缓存
                if cache_key and cache_key in processed_cache:
                    frame.quality_score, frame.filter_reason = processed_cache[cache_key]
                    updated_frames_for_slice.append(frame.model_dump())
                    continue

                if not abs_path.exists():
                    logger.warning(f"Frame Probe: Frame file not found: {abs_path}")
                    frame.quality_score = 0.0  # 标记为低质量
                    frame.filter_reason = "file_not_found"
                    updated_frames_for_slice.append(frame.model_dump())
                    continue

                try:
                    img = cv2.imread(str(abs_path))
                    if img is None:
                        logger.warning(f"Could not read image: {abs_path}")
                        frame.quality_score = 0.0
                        frame.filter_reason = "image_read_error"
                        updated_frames_for_slice.append(frame.model_dump())
                        continue

                    # 2. 模糊度 (Laplacian Variance)
                    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                    # 避免全黑或全白图像导致方差为0
                    if gray.var() == 0:
                        fm = 0.0
                    else:
                        fm = cv2.Laplacian(gray, cv2.CV_64F).var()  # 模糊度分数，越高越清晰

                    # 3. 黑/白帧检测
                    is_black, is_white = FrameProbeService._is_black_or_white_frame(gray)

                    if is_black:
                        frame.filter_reason = "black_frame"
                    elif is_white:
                        frame.filter_reason = "white_frame"
                    elif fm < 100.0:  # 假设低于100为极度模糊
                        frame.filter_reason = "blurry_frame"

                    # 计算可用性分数：如果有过滤原因，分数为0
                    frame.quality_score = 0.0 if frame.filter_reason else round(fm / 1000.0, 4)

                except Exception as e:
                    logger.error(f"Frame Probe Failed for {abs_path}: {str(e)}")
                    frame.quality_score = 0.0
                    frame.filter_reason = f"error: {str(e)}"

                # 写入缓存
                if cache_key:
                    processed_cache[cache_key] = (frame.quality_score, frame.filter_reason)
                updated_frames_for_slice.append(frame.model_dump())

            updated_keyframe_map[slice_id] = updated_frames_for_slice

        logger.info(
            f"Frame Probe Finished: {len(updated_keyframe_map)} slices analyzed. Cache hits: {len(keyframe_map) - len(processed_cache)} (approx)"  # noqa: E501
        )
        return updated_keyframe_map

    @staticmethod
    def _is_black_or_white_frame(
        gray_img: np.ndarray, black_thresh=10, white_thresh=245, std_thresh=5
    ) -> Tuple[bool, bool]:
        """
        [内部方法] 通过均值和标准差检测黑/白帧。

        Args:
            gray_img: 灰度图像 (numpy array)。
            black_thresh: 黑帧均值阈值。
            white_thresh: 白帧均值阈值。
            std_thresh: 标准差阈值 (用于判断是否纯色)。

        Returns:
            (is_black, is_white)
        """
        mean = gray_img.mean()
        std = gray_img.std()

        is_black = mean < black_thresh and std < std_thresh
        is_white = mean > white_thresh and std < std_thresh
        return is_black, is_white
