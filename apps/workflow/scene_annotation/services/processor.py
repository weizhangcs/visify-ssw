import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict

# 引入重构后的 Uploader
from .slice_extractor import SliceExtractorService
from .uploader import TicketUploader, VSSCloudService

logger = logging.getLogger(__name__)


class EdgeScenePreprocessor:
    """
    [Edge Facade] 场景预标注流程总管
    """

    def __init__(self, work_dir: Path, asset_id: str, media_id: str):
        self.work_dir = work_dir
        self.asset_id = asset_id
        self.media_id = media_id

        # 初始化 Cloud Client 用于最后的 JSON 上传
        self.cloud_service = VSSCloudService()

        # 初始化 Uploader (内部会自动加载 IntegrationSettings)
        self.uploader = TicketUploader(asset_id, media_id)

    def process(self, video_path: str, ass_path: str) -> Dict[str, Any]:
        # --- Step 1: 生产 (M1) ---
        logger.info(">>> Phase 2.1: Slicing & Extracting...")
        extractor = SliceExtractorService(output_root=self.work_dir, max_workers=8)
        raw_slices = extractor.run(video_path, ass_path)

        # 收集图片路径
        all_image_paths = []
        for s in raw_slices:
            for f in s.get("frames", []):
                p = Path(f["path"])
                if p.exists():
                    all_image_paths.append(p)

        # --- Step 2: 传输 (M2) ---
        logger.info(f">>> Phase 2.2: Uploading {len(all_image_paths)} images via Ticket...")
        path_mapping = self.uploader.upload_files(all_image_paths)

        # --- Step 3: 清洗 ---
        logger.info(">>> Phase 2.3: Rewriting paths...")
        for s in raw_slices:
            for f in s.get("frames", []):
                local_p_str = str(f["path"])
                if local_p_str in path_mapping:
                    f["path"] = path_mapping[local_p_str]
                else:
                    f["error"] = "upload_failed"

        # --- Step 4: 索引上传 ---
        logger.info(">>> Phase 2.4: Uploading metadata json...")

        meta_filename = f"raw_slices_{uuid.uuid4()}.json"
        meta_path = self.work_dir / meta_filename
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(raw_slices, f, ensure_ascii=False)

        # 使用 self.cloud_service 进行普通文件上传
        with open(meta_path, "rb") as f:
            resp = self.cloud_service.post_file("/api/v1/files/upload", files={"file": f})

        cloud_json_path = resp.get("relative_path")
        if not cloud_json_path:
            raise RuntimeError("Failed to upload metadata json")

        logger.info(f"✅ Edge Processing Complete. Metadata: {cloud_json_path}")

        return {"slices_file_path": cloud_json_path, "total_slices": len(raw_slices), "video_path": video_path}
