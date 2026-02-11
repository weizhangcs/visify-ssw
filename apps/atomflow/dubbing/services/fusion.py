import logging
from pathlib import Path
from typing import Dict, List

import librosa
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class AudioVisualFusionService:
    """
    [物理算子] 视听融合服务 (Active Speaker Detection)
    """

    @staticmethod
    def run(metadata: List[Dict], face_csv_path: Path, audio_path: Path) -> List[Dict]:
        logger.info("Fusion: Aligning Audio & Visual streams...")

        engine = FusionEngineHelper()
        fused_metadata = engine.run(metadata, str(face_csv_path), str(audio_path))

        return fused_metadata


class FusionEngineHelper:
    def run(self, metadata, face_csv_path, audio_path):
        df_face = pd.read_csv(face_csv_path)
        y, sr = librosa.load(audio_path, sr=16000)

        fused_metadata = []

        for seg in metadata:
            start_t = seg["start"]
            end_t = seg["end"]

            segment_faces = df_face[(df_face["timestamp"] >= start_t) & (df_face["timestamp"] <= end_t)]

            if segment_faces.empty:
                seg["speaker"] = "OFF_SCREEN"
                seg["fusion_score"] = 0.0
                fused_metadata.append(seg)
                continue

            timestamps = np.sort(segment_faces["timestamp"].unique())
            if len(timestamps) < 5:
                seg["speaker"] = "UNCERTAIN_SHORT"
                fused_metadata.append(seg)
                continue

            audio_energy = []
            window_size = int(0.04 * sr)
            for t in timestamps:
                sample_idx = int(t * sr)
                start_s = max(0, sample_idx - window_size // 2)
                end_s = min(len(y), sample_idx + window_size // 2)
                chunk = y[start_s:end_s]
                rms = np.sqrt(np.mean(chunk**2)) if len(chunk) > 0 else 0
                audio_energy.append(rms)

            audio_energy = np.array(audio_energy)
            if np.std(audio_energy) > 1e-6:
                audio_energy = (audio_energy - np.mean(audio_energy)) / np.std(audio_energy)

            best_pid = -1
            best_corr = -1.0
            unique_pids = segment_faces["person_id"].unique()

            for pid in unique_pids:
                if pid == -1:
                    continue
                person_data = segment_faces[segment_faces["person_id"] == pid]
                mouth_curve = [
                    person_data[person_data["timestamp"] == t].iloc[0]["mouth_ratio"]
                    if not person_data[person_data["timestamp"] == t].empty
                    else 0.0
                    for t in timestamps
                ]
                mouth_curve = np.array(mouth_curve)
                if np.std(mouth_curve) > 1e-6:
                    mouth_curve = (mouth_curve - np.mean(mouth_curve)) / np.std(mouth_curve)
                corr = np.corrcoef(audio_energy, mouth_curve)[0, 1]
                if corr > best_corr:
                    best_corr = corr
                    best_pid = pid

            if best_pid != -1 and best_corr > 0.15:
                seg["speaker"] = f"PERSON_{best_pid:02d}"  # noqa: E231
                seg["fusion_score"] = float(best_corr)
            else:
                seg["speaker"] = "OFF_SCREEN_OR_UNCERTAIN"
                seg["fusion_score"] = float(best_corr)

            fused_metadata.append(seg)

        return fused_metadata
