import json
import logging
import os
from typing import Dict

import librosa
import numpy as np
from faster_whisper import WhisperModel

from apps.atomflow.dubbing import constants

logger = logging.getLogger(__name__)


class PerceptionAnalyzerService:
    """
    [物理算子] 感知分析服务 (ASR + Features)
    """

    @staticmethod
    def run(audio_path: str, output_path: str = None) -> Dict:
        logger.info(f"Perception: Analyzing {os.path.basename(audio_path)}...")

        analyzer = PerceptionAnalyzerHelper(whisper_path=constants.WHISPER_PATH)
        segments = analyzer.transcribe(audio_path)
        metadata = analyzer.analyze_audio_features(audio_path, segments)
        logger.info(f"Perception analysis completed. Found {len(segments)} segments.")

        result = {"segments": segments, "metadata": metadata}

        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            logger.info(f"Perception result saved to {output_path}")

        return result


class PerceptionAnalyzerHelper:
    def __init__(self, whisper_path):
        self.asr_model = WhisperModel(whisper_path, device="cuda", compute_type="float16")

    def transcribe(self, audio_path):
        segments_generator, _ = self.asr_model.transcribe(
            audio_path, beam_size=5, vad_filter=True, word_timestamps=True
        )

        results = []
        for s in segments_generator:
            # faster_whisper 返回的是 avg_logprob (对数概率)，转换为 0-1 的置信度
            confidence = float(np.exp(s.avg_logprob))

            results.append(
                {
                    "start": s.start,
                    "end": s.end,
                    "text": s.text.strip(),
                    "confidence": confidence,  # 添加置信度打分
                    "no_speech_prob": s.no_speech_prob,  # 可选：非人声概率
                }
            )
        return results

    def analyze_audio_features(self, audio_path, segments):
        y_librosa, _ = librosa.load(audio_path, sr=16000)
        results = []
        for seg in segments:
            start_sample = int(seg["start"] * 16000)
            end_sample = int(seg["end"] * 16000)
            rms, centroid = 0.0, 0.0

            if end_sample > start_sample:
                y_seg = y_librosa[start_sample:end_sample]
                if len(y_seg) > 0:
                    rms = float(np.mean(librosa.feature.rms(y=y_seg)))
                    centroid = float(np.mean(librosa.feature.spectral_centroid(y=y_seg, sr=16000)))

            results.append(
                {**seg, "audio_features": {"energy_rms": rms, "spectral_centroid": centroid}, "speaker": "PENDING"}
            )
        return results
