import logging
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

# 引入当前业务模型
from .models import SceneAnnotationJob, SceneAnnotationProject

# [新增] 引入资产模型 (请根据您项目的实际结构调整 import 路径)
try:
    from apps.assets.models import Asset
except ImportError:
    # 兼容性处理，防止 IDE 报错，运行时必须存在
    Asset = None

from apps.workflow.character_annotation.services.edge_scene_processor import EdgeScenePreprocessor
from apps.workflow.character_annotation.services.ticket_uploader import VSSCloudService

logger = logging.getLogger(__name__)


@shared_task(bind=True, queue="worker-media")
def run_scene_annotation_pipeline(
    self, project_id: int, media_id: str, video_path: str, ass_path: str, work_dir_root: str = None
):
    """
    执行场景预标注全流程
    [Fix]: 动态从 Asset 模型获取元数据 (type, genre, lang)
    """
    job_id = None
    try:
        # 1. 初始化 Job 与 Project
        project = SceneAnnotationProject.objects.get(id=project_id)

        # [关键修复] 回溯查询 Asset 数据
        if Asset:
            try:
                asset_obj = Asset.objects.get(id=project.asset_id)
            except ObjectDoesNotExist:
                logger.error(f"Asset {project.asset_id} not found for Project {project_id}")
                raise ValueError(f"Bound Asset {project.asset_id} does not exist.")
        else:
            # 如果没有 Asset 模型定义的 fallback (仅供调试，生产环境应报错)
            logger.warning("Asset model not imported correctly.")
            asset_obj = None

        job = SceneAnnotationJob.objects.create(
            project=project, media_id=media_id, status=SceneAnnotationJob.Status.PROCESSING
        )
        job_id = job.id
        logger.info(f"[Job {job_id}] Starting Pipeline for Asset: {asset_obj.title if asset_obj else 'Unknown'}")

        # 2. 准备工作目录
        if work_dir_root:
            work_dir = Path(work_dir_root) / str(job_id)
        else:
            work_dir = Path(settings.MEDIA_ROOT) / "scene_annotation" / "jobs" / str(job_id)

        work_dir.mkdir(parents=True, exist_ok=True)

        # 3. 执行 Edge Processing (耗时操作)
        processor = EdgeScenePreprocessor(work_dir=work_dir, asset_id=str(project.asset_id), media_id=str(media_id))

        context = processor.process(video_path, ass_path)
        slices_cloud_path = context["slices_file_path"]

        # 4. 组装动态 Payload
        # [关键修复] 从 asset_obj 取值，而非硬编码
        # 请根据您的 Asset 模型字段名进行微调 (例如是 .genre 还是 .content_genre)

        payload_data = {
            # 基础信息
            "video_title": asset_obj.title if asset_obj else (project.title or f"Asset-{project.asset_id}"),
            # 业务元数据 (从 Asset 继承)
            "asset_type": getattr(asset_obj, "asset_type", "feature_film"),  # e.g. movie, episode
            "content_genre": getattr(asset_obj, "content_genre", "drama"),  # e.g. crime_thriller
            "lang": getattr(asset_obj, "language", "en"),  # e.g. en, zh
            # 技术参数 (切片路径)
            "slices_file_path": slices_cloud_path,
            # 模型配置 (可从 IntegrationSettings 或 Project 配置读取，暂时保持硬编码或默认)
            "visual_model": "gemini-2.5-flash",
            "text_model": "gemini-2.5-flash",
        }

        task_payload = {"task_type": "scene_pre_annotator", "payload": payload_data}

        # 5. 提交任务
        logger.info(
            f"[Job {job_id}] Submitting task to Cloud with payload: {payload_data['video_title']} ({payload_data['lang']})"  # noqa: E501
        )

        client = VSSCloudService()
        resp = client.post("/api/v1/tasks/", task_payload)

        cloud_task_id = resp.get("id")
        if not cloud_task_id:
            raise RuntimeError("Cloud response missing task ID")

        # 6. 更新状态
        job.cloud_task_id = cloud_task_id
        job.status = SceneAnnotationJob.Status.CLOUD_SUBMITTED
        job.save()

        return f"Submitted: {cloud_task_id}"

    except Exception as e:
        logger.error(f"[Job {job_id}] Pipeline Failed: {e}", exc_info=True)
        if job_id:
            SceneAnnotationJob.objects.filter(id=job_id).update(
                status=SceneAnnotationJob.Status.FAILED, error_message=str(e)[:5000]
            )
        raise e
