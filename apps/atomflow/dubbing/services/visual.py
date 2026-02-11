import json
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import onnxruntime as ort
import pandas as pd
import torch
from insightface.app import FaceAnalysis
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import Normalizer

from apps.atomflow.dubbing import constants, utils

logger = logging.getLogger(__name__)


class VisualAnalysisService:
    """
    [物理算子] 视觉分析服务 (Face Detection + Clustering)
    """

    @staticmethod
    def run(video_path: Path, output_dir: Path, temp_dir: Path, mask_path: Optional[str] = None) -> str:
        logger.info(f"Visual: Analyzing {video_path.name}...")
        output_dir.mkdir(parents=True, exist_ok=True)
        temp_dir.mkdir(parents=True, exist_ok=True)

        analyzer = VisualAnalyzerHelper(model_dir=constants.INSIGHTFACE_MODEL_DIR, mask_path=mask_path)
        csv_path, _ = analyzer.run(str(video_path), str(output_dir), str(temp_dir), mask_path)

        del analyzer
        utils.cleanup_gpu()

        return csv_path


class VisualAnalyzerHelper:
    def __init__(self, model_dir, mask_path=None):
        # 显式加载 landmark_2d_106 用于嘴型计算
        # [Optimization] 抑制 ONNX Runtime 的冗长日志
        ort.set_default_logger_severity(3)

        self.app = FaceAnalysis(
            name="buffalo_l",
            root=model_dir,
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            allowed_modules=["detection", "recognition", "landmark_2d_106"],
        )
        self.app.prepare(ctx_id=0, det_size=(640, 640))

        # 加载 Gating Mask (如果提供)
        self.speech_mask = None
        self.sr = 16000  # Gating 固定采样率
        if mask_path and os.path.exists(mask_path):
            try:
                logger.info(f"   [Visual] Loading gating mask from {mask_path}...")
                masks = torch.load(mask_path, map_location="cpu", weights_only=True)
                if "perception" in masks:
                    self.speech_mask = masks["perception"].float().numpy().flatten()
            except Exception as e:
                logger.warning(f"   [Visual] Failed to load mask: {e}")

    def run(self, video_path, output_dir, temp_dir, mask_path=None):
        cap = utils.FFmpegVideoReader(video_path)
        fps = cap.fps
        # total_frames = cap.total_frames

        SAMPLE_INTERVAL = 1  # [Optimization] 既然已有 Gating 过滤，有效片段内应逐帧分析以获取更细腻的嘴型/表情数据
        face_full_data = []
        all_embeddings = []

        temp_crops_dir = os.path.join(temp_dir, "face_crops_cache")
        if os.path.exists(temp_crops_dir):
            shutil.rmtree(temp_crops_dir)
        os.makedirs(temp_crops_dir)

        global_face_idx = 0
        frame_idx = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            current_time = frame_idx / fps

            # [Optimization] 语义门控过滤 (如果提供了 Audio Mask)
            if self.speech_mask is not None:
                # 映射到音频采样点 (假设 16kHz)
                sample_idx = int((frame_idx / fps) * self.sr)
                # 宽松边界检查
                if 0 <= sample_idx < len(self.speech_mask):
                    # 阈值判定：如果当前时刻人声概率极低 (<0.1)，则跳过 Visual Analysis
                    if self.speech_mask[sample_idx] < 0.1:
                        frame_idx += 1
                        continue

            if frame_idx % SAMPLE_INTERVAL == 0:
                faces = self.app.get(frame)
                if faces:
                    for face in faces:
                        score = float(face.det_score)
                        bbox = face.bbox.astype(int).tolist()
                        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]

                        if score < 0.8 or w < 80 or h < 80:
                            continue

                        mouth_ratio = 0.0
                        if face.landmark_2d_106 is not None:
                            lmk = face.landmark_2d_106
                            mouth_points = lmk[52:72]
                            mouth_h = np.max(mouth_points[:, 1]) - np.min(mouth_points[:, 1])
                            mouth_ratio = mouth_h / h

                        embedding = face.embedding.astype(np.float32)

                        face_instance = {
                            "frame_idx": frame_idx,
                            "timestamp": current_time,
                            "bbox": bbox,
                            "score": score,
                            "embedding": embedding,
                            "mouth_ratio": mouth_ratio,
                            "embedding_preview": embedding[:5].tolist(),
                        }
                        face_full_data.append(face_instance)
                        all_embeddings.append(embedding)

                        face_img = frame[
                            max(0, bbox[1]) : min(frame.shape[0], bbox[3]),
                            max(0, bbox[0]) : min(frame.shape[1], bbox[2]),
                        ]
                        if face_img.size > 0:
                            cv2.imwrite(os.path.join(temp_crops_dir, f"{global_face_idx}.jpg"), face_img)
                        global_face_idx += 1

            frame_idx += 1

        cap.release()

        # Clustering
        person_ids = []
        if len(all_embeddings) > 0:
            normalizer = Normalizer(norm="l2")
            all_embeddings_normalized = normalizer.fit_transform(np.array(all_embeddings))
            dbscan = DBSCAN(eps=0.45, min_samples=5, metric="cosine", algorithm="brute")
            person_ids = dbscan.fit_predict(all_embeddings_normalized)

            max_cluster_id = np.max(person_ids) if len(person_ids) > 0 else 0
            for i in range(len(person_ids)):
                if person_ids[i] == -1:
                    max_cluster_id += 1
                    person_ids[i] = max_cluster_id

        face_data_list = []
        for idx, face_instance in enumerate(face_full_data):
            pid = int(person_ids[idx]) if idx < len(person_ids) else -1
            face_data_list.append(
                {
                    "frame_idx": face_instance["frame_idx"],
                    "timestamp": face_instance["timestamp"],
                    "person_id": pid,
                    "bbox": json.dumps(face_instance["bbox"]),
                    "score": face_instance["score"],
                    "mouth_ratio": face_instance["mouth_ratio"],
                    "embedding_preview": json.dumps(face_instance["embedding_preview"]),
                }
            )

        df = pd.DataFrame(face_data_list)
        csv_path = os.path.join(output_dir, "face_index_with_clusters.csv")
        df.to_csv(csv_path, index=False)

        if os.path.exists(temp_crops_dir):
            shutil.rmtree(temp_crops_dir)

        return csv_path, df
