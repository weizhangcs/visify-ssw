import logging
from pathlib import Path

from django.conf import settings
from django.core.files import File

from apps.media_assets.models import Asset, Media

logger = logging.getLogger(__name__)


class IngestionService:
    """
    媒资摄入服务 (Ingestion Service)
    负责处理从 Batch Upload 目录扫描文件、解析元数据、注册 Media 实体
    以及初始化后续 Refinery 流水线的核心业务逻辑。
    """

    def execute(self, asset_id: str) -> str:
        """
        执行摄入流程
        :param asset_id: Asset UUID
        :return: 结果消息
        """
        # Lazy import to avoid circular dependency (保持原有设计)
        from apps.atomflow.refinery.models import Material, RefineryAtomPipeline, RefineryAtomRule

        asset = None
        try:
            asset = Asset.objects.get(id=asset_id)
            asset.upload_status = "uploading"
            asset.save(update_fields=["upload_status"])

            upload_dir = Path(settings.MEDIA_ROOT) / "batch_uploads" / str(asset.id)
            if not upload_dir.exists():
                raise FileNotFoundError(f"未找到 Asset ID: {asset.id} 的上传目录: {upload_dir}")

            video_files = list(upload_dir.glob("*.mp4")) + list(upload_dir.glob("*.mov"))
            logger.info(f"在 {upload_dir} 中找到 {len(video_files)} 个视频文件。")

            # 获取默认规则 (如果存在)
            default_rule = RefineryAtomRule.objects.first()
            if not default_rule:
                logger.warning("系统未配置 RefineryAtomRule，将跳过 Pipeline 创建。")

            for video_path in video_files:
                base_name = video_path.stem
                srt_path = upload_dir / f"{base_name}.srt"

                digits = "".join([char for char in base_name if char.isdigit()])

                # [Debug Probe]
                logger.info(f"[Ingest Probe] File: {base_name}, Extracted Digits: '{digits}'")

                # [Fix] 防止 sequence_number 超出 Postgres Integer 范围
                if digits:
                    if len(digits) > 9:
                        sequence_number = int(digits[-9:])
                    else:
                        sequence_number = int(digits)
                else:
                    sequence_number = 0

                # --- 核心逻辑：创建 Media 对象并关联到 Asset ---
                media, created = Media.objects.get_or_create(
                    asset=asset, sequence_number=sequence_number, defaults={"title": base_name}
                )
                logger.info(f"已创建/找到 Media: {media.title}")

                with video_path.open("rb") as f:
                    media.source_video.save(video_path.name, File(f), save=False)
                if srt_path.exists():
                    with srt_path.open("rb") as f:
                        media.source_subtitle.save(srt_path.name, File(f), save=False)
                media.save()

                # --- 核心逻辑：自动创建 Refinery Pipeline ---
                if default_rule:
                    material, _ = Material.objects.get_or_create(media=media)

                    # 仅当 Pipeline 不存在时创建
                    if not hasattr(material, "pipeline"):
                        RefineryAtomPipeline.objects.create(
                            name=f"Refinery-{media.title}",
                            rule=default_rule,
                            material=material,
                            target_id=str(material.id),
                            status="PENDING",
                        )
                        logger.info(f"Pipeline created for {media.title}")

            asset.upload_status = "completed"
            asset.save(update_fields=["upload_status"])
            logger.info(f"Asset ID: {asset.id} 的所有文件已派发处理。")
            return f"Ingestion complete for Asset {asset.id}"

        except Exception as e:
            logger.error(f"为 Asset ID: {asset_id} 批量加载文件时发生错误: {e}", exc_info=True)
            if asset:
                asset.upload_status = "failed"
                asset.save(update_fields=["upload_status"])
            raise
