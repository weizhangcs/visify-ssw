import json
import logging
from pathlib import Path

from django.conf import settings

from apps.workflow.common.cloud_client import CloudApiService

# [修复 Crash 根源] 正确引用 Asset/Media 模型
from apps.workflow.scene_annotation.models import SceneAnnotationJob, SceneAnnotationProject

from ...character_annotation.models import CharacterAnnotationJob
from ...common.baseJob import BaseJob

# 引用刚迁移过来的组件
from .processor import EdgeScenePreprocessor

logger = logging.getLogger(__name__)


class SceneAnnotationService:
    """
    [Service Layer] 场景标注核心业务服务 (V3.0 Final)
    包含：严格流水线校验、异常持久化、项目状态联动。
    """

    @classmethod
    def launch_project(cls, project_id: str) -> int:
        """
        [Business Logic] 启动项目级任务 (Controller)
        职责：
        1. 遍历 Asset 下的所有 Media
        2. 幂等创建/获取 Jobs
        3. 根据状态过滤，批量触发异步 Task
        4. 更新 Project 级状态

        返回: 成功触发的任务数量
        """
        # 延迟导入，解决循环依赖
        from apps.workflow.scene_annotation.tasks import run_scene_annotation_pipeline

        project = SceneAnnotationProject.objects.get(id=project_id)

        # 1. 获取媒体列表
        medias = project.asset.medias.all().order_by("sequence_number")
        if not medias.exists():
            return 0  # 或者抛出特定异常，视业务需求而定

        triggered_count = 0

        for media in medias:
            # 2. 幂等创建 Job
            job, created = SceneAnnotationJob.objects.get_or_create(
                project=project, media=media, defaults={"status": SceneAnnotationJob.STATUS.PENDING}
            )

            # 3. 状态检查与触发
            # 允许重试的状态：PENDING, FAILED (项目级旧状态), ERROR (任务级新状态)
            if job.status in [SceneAnnotationJob.STATUS.PENDING, "FAILED", SceneAnnotationJob.STATUS.ERROR]:
                # 异步调度
                run_scene_annotation_pipeline.delay(job_id=str(job.id))
                triggered_count += 1

        # 4. 更新项目状态
        if triggered_count > 0:
            if project.status != SceneAnnotationProject.STATUS.PROCESSING:
                project.status = SceneAnnotationProject.STATUS.PROCESSING
                project.save(update_fields=["status"])
                logger.info(f"[SceneService] Project {project.id} status set to PROCESSING")

        return triggered_count

    @classmethod
    def execute_pipeline(cls, job_id: str):
        logger.info(f"[SceneService] Starting pipeline for Job {job_id}")
        job = None

        try:
            # 1. 数据加载
            job = SceneAnnotationJob.objects.select_related("project", "media", "project__asset").get(id=job_id)

            # [清除旧错误] 重试时清空历史报错
            job.error_message = None

            project = job.project
            asset = project.asset
            media = job.media

            if job.status not in [SceneAnnotationJob.STATUS.PENDING, SceneAnnotationJob.STATUS.ERROR]:
                logger.warning(f"Job {job_id} status is {job.status}, skipping.")
                return

            job.start()
            job.save()

            # 2. 路径准备 (Intelligent Selection)

            # [优化 A] 视频源：使用 Proxy (get_best_processing_path)
            video_path = media.get_best_processing_path()
            if not video_path:
                raise ValueError(f"Media {media.id} 无法获取有效的视频处理路径 (Proxy 或 Source 均缺失)。")

            # [依赖 B] 字幕源：强依赖 Character Annotation 产出的 ASS
            ass_path = ""

            # 查找已完成的角色标注任务
            char_job = (
                CharacterAnnotationJob.objects.filter(media=media, status=BaseJob.STATUS.COMPLETED)
                .order_by("-modified")
                .first()
            )

            if char_job and char_job.output_ass_file:
                if char_job.output_ass_file.storage.exists(char_job.output_ass_file.name):
                    ass_path = char_job.output_ass_file.path
                    logger.info(f"Using AI-Enhanced ASS Subtitle: {ass_path}")
                else:
                    logger.error(
                        f"Character Job {char_job.id} marked COMPLETED but file missing: {char_job.output_ass_file.name}"  # noqa : E501
                    )

            # [核心修正] 移除 SRT 兜底，实施强校验
            if not ass_path:
                raise ValueError(f"Media {media.id} 缺少 AI 角色标注生成的 ASS 字幕。请先执行角色标注任务 (Character Annotation)。")

            # 准备工作目录
            work_dir = Path(settings.MEDIA_ROOT) / "scene_annotation" / "jobs" / str(job.id)
            work_dir.mkdir(parents=True, exist_ok=True)

            # 3. 执行 Edge Processing
            logger.info(f"[SceneService] Processor Input -> Video: {video_path}, Sub: {ass_path}")

            processor = EdgeScenePreprocessor(work_dir=work_dir, asset_id=str(asset.id), media_id=str(media.id))

            context = processor.process(str(video_path), str(ass_path))  # 确保转为 str
            slices_cloud_path = context.get("slices_file_path")

            if not slices_cloud_path:
                raise RuntimeError("Edge processor returned no 'slices_file_path'.")

            # 4. 组装 Cloud Payload
            payload = {
                "video_title": f"{asset.title}",
                "asset_type": asset.asset_type,
                "content_genre": asset.content_genre,
                "lang": asset.language.split("-")[0],
                "slices_file_path": slices_cloud_path,
                "visual_model": "gemini-2.5-flash",
                "text_model": "gemini-2.5-flash",
            }

            # 5. 提交云端任务
            logger.info(f"[SceneService] Submitting: {payload['video_title']}")
            cloud_client = CloudApiService()
            success, response = cloud_client.create_task("scene_pre_annotator", payload)

            if not success:
                raise RuntimeError(f"Cloud API failed: {response}")

            cloud_task_id = response.get("id")
            if not cloud_task_id:
                raise ValueError("Cloud API response missing 'id'.")

            job.cloud_task_id = cloud_task_id
            job.save(update_fields=["cloud_task_id", "modified"])

            # 6. 轮询
            from apps.workflow.common.tasks import poll_cloud_task_general

            poll_cloud_task_general.delay(
                model_name="SceneAnnotationJob",
                job_id=str(job.id),
                cloud_task_id=cloud_task_id,
                on_complete_task_name="apps.workflow.scene_annotation.tasks.finalize_scene_annotation",
                on_complete_kwargs={},
            )

        except Exception as e:
            logger.error(f"[SceneService] Job {job_id} Error: {e}", exc_info=True)
            if "job" in locals():
                job.fail()
                # [核心修复 1] 记录错误信息
                job.error_message = str(e)
                job.save()
                # [核心修复 2] 触发项目状态更新 (即使失败也要检查是否全剧终)
                cls._update_project_status(job.project.id)
            raise e

    @classmethod
    def finalize_pipeline(cls, job_id: str, cloud_task_data: dict):
        """
        [Business Logic] 处理云端任务回调
        职责：下载结果 -> 校验 -> 解析 -> 落库
        """
        logger.info(f"[SceneService] Finalizing Job {job_id}...")

        try:
            job = SceneAnnotationJob.objects.get(id=job_id)

            # [错误处理] 检查 Cloud 返回的 status
            cloud_status = cloud_task_data.get("status")
            if cloud_status == "FAILED":
                error_msg = cloud_task_data.get("error", "Unknown cloud error")
                raise RuntimeError(f"Cloud Task Reported Failure: {error_msg}")

            # 1. 提取下载地址 (URL Parsing Logic)
            download_url = cloud_task_data.get("download_url")
            # 兼容 result 嵌套
            if not download_url and isinstance(cloud_task_data.get("result"), dict):
                download_url = cloud_task_data.get("result").get("download_url")

            if not download_url:
                raise ValueError(f"Missing 'download_url' in callback data: {cloud_task_data}")

            # 2. 执行下载 (I/O Operation)
            logger.info(f"[SceneService] Downloading result from: {download_url}")
            cloud = CloudApiService()
            success, content_bytes = cloud.download_task_result(download_url)

            if not success or not content_bytes:
                raise RuntimeError(f"Failed to download result from {download_url}")

            # 3. 解析与校验 (Validation Logic)
            try:
                result_json = json.loads(content_bytes.decode("utf-8"))
            except json.JSONDecodeError as e:
                raise ValueError(f"Downloaded content is not valid JSON: {e}")

            # 4. 数据落库 (Persistence)
            job.result = result_json
            job.complete()  # FSM: PROCESSING -> COMPLETED
            job.save()

            logger.info(
                f"[SceneService] Job {job_id} finalized successfully. Scene Count: {len(result_json.get('scenes', []))}"
            )

            # [核心修复 3] 成功后触发项目状态检查
            cls._update_project_status(job.project.id)

        except Exception as e:
            logger.error(f"[SceneService] Finalize error for Job {job_id}: {e}", exc_info=True)
            # 在 Service 层处理业务异常的状态流转
            if "job" in locals():
                job.fail()
                # 既然是 Service 层，这里可以安全地写入错误信息（如果模型支持）
                # [核心修复 1] 记录错误信息
                job.error_message = f"Finalize Phase Error: {str(e)}"
                job.save()
                # [核心修复 2] 失败也要触发项目检查
                cls._update_project_status(job.project.id)
            raise e

    @classmethod
    def _update_project_status(cls, project_id):
        """
        [Helper] 检查并更新项目级状态
        逻辑：
        1. 如果有任何 Job 还在 PENDING/PROCESSING，项目保持 PROCESSING。
        2. 如果所有 Job 都结束了，且有任何一个 ERROR，项目设为 FAILED。
        3. 如果所有 Job 都 COMPLETED，项目设为 COMPLETED。
        """
        project = SceneAnnotationProject.objects.get(id=project_id)
        all_jobs = project.scene_annotation_jobs.all()  # 注意 related_name

        total = all_jobs.count()
        if total == 0:
            return

        has_processing = all_jobs.filter(
            status__in=[BaseJob.STATUS.PENDING, BaseJob.STATUS.PROCESSING, BaseJob.STATUS.QUEUED]
        ).exists()
        has_error = all_jobs.filter(status=BaseJob.STATUS.ERROR).exists()

        new_status = project.status
        if has_processing:
            new_status = "PROCESSING"
        elif has_error:
            new_status = "FAILED"
        else:
            new_status = "COMPLETED"

        if project.status != new_status:
            project.status = new_status
            project.save(update_fields=["status"])
            logger.info(f"[SceneService] Project {project.name} status updated to {new_status}")
