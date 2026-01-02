from pathlib import Path

from ...schemas import TechMeta


class ProbeContextMixin:
    def _payload_probe(self, target):
        proxy_rel = target.proxy_video
        abs_proxy_path = self.media_root / proxy_rel
        temp_wav_path = Path(f"/tmp/atomflow_probe_{target.id}.wav")

        return {"proxy_path": str(abs_proxy_path), "temp_wav_path": str(temp_wav_path)}

    def _handle_probe(self, target, result):
        target.duration = result.get("duration", 0.0)
        target.tech_meta = TechMeta(**result.get("tech_meta", {})).model_dump()
        target.waveform_data = result.get("waveform_data", [])

    def _check_probe_ready(self, target):
        return bool(target.proxy_video)

    def _check_probe_done(self, target):
        return target.duration > 0
