# apps/workflow/creative/tasks.py

import json
import logging
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile

from apps.workflow.common.tasks import poll_cloud_task

from .jobs import CreativeJob
from .models import CreativeProject
from .services.actions import CreativeTaskAction
from .services.payloads import PayloadBuilder
from .services.synthesis_service import SynthesisService

logger = logging.getLogger(__name__)


# ==============================================================================
# 1. 生成解说词 (Narration - Step 1)
# ==============================================================================


@shared_task(name="apps.workflow.creative.tasks.start_narration_task")
def start_narration_task(project_id: str, config: dict = None, **kwargs):
    action = None
    job = None
    try:
        action = CreativeTaskAction(project_id)
        blueprint_path = action.ensure_blueprint_uploaded()

        job = action.create_job(CreativeJob.TYPE.GENERATE_NARRATION, config)
        action.update_project_status(CreativeProject.Status.NARRATION_RUNNING)

        asset_name, asset_id = action.get_asset_info()
        payload = PayloadBuilder.build_narration_payload(
            asset_name=asset_name, asset_id=asset_id, blueprint_path=blueprint_path, raw_config=config
        )

        logger.info(f"[NarrationTask] Payload: \n{json.dumps(payload, ensure_ascii=False)}")

        success, task_data = action.cloud_service.create_task("GENERATE_NARRATION", payload)
        if not success:
            raise Exception(task_data.get("message"))

        job.cloud_task_id = task_data["id"]
        job.save()

        poll_cloud_task.delay(
            job_id=job.id,
            cloud_task_id=task_data["id"],
            on_complete_task_name="apps.workflow.creative.tasks.finalize_narration_task",
            on_complete_kwargs={},
        )

    except Exception as e:
        logger.error(f"[NarrationTask] Failed: {e}", exc_info=True)
        if job:
            job.fail()
            job.save()
        if action:
            action.update_project_status(CreativeProject.Status.FAILED)


@shared_task(name="apps.workflow.creative.tasks.finalize_narration_task")
def finalize_narration_task(job_id: str, cloud_task_data: dict, **kwargs):
    """
    [Callback] 解说词任务完成回调。
    """
    try:
        job = CreativeJob.objects.get(id=job_id)
        action = CreativeTaskAction(str(job.project.id))

        action.handle_callback_download(
            job_id=job_id,
            cloud_data=cloud_task_data,
            target_file_field_name="narration_script_file",
            filename_prefix="narration_script",
        )

        action.update_project_status(CreativeProject.Status.NARRATION_COMPLETED)

        # [核心修复] 3. 自动化链式触发
        if action.project.auto_config:
            auto_conf = action.project.auto_config
            localize_conf = auto_conf.get("localize", {})

            # 判断是否有有效的本地化配置 (target_lang 存在)
            if localize_conf and localize_conf.get("target_lang"):
                logger.info(f"[AutoPilot] 检测到本地化配置 (Target: {localize_conf.get('target_lang')})，启动 Step 1.5...")
                # 局部导入避免循环引用
                from .tasks import start_localize_task

                start_localize_task.delay(project_id=str(job.project.id), config=localize_conf)
            else:
                logger.info("[AutoPilot] 未检测到本地化配置，直接启动 Step 2 (配音)...")
                from .tasks import start_audio_task

                start_audio_task.delay(project_id=str(job.project.id), config=auto_conf.get("audio", {}))

    except Exception as e:
        logger.error(f"[NarrationFinal] Failed: {e}", exc_info=True)


# ==============================================================================
# 2. 本地化 (Localization - Step 1.5)
# ==============================================================================


@shared_task(name="apps.workflow.creative.tasks.start_localize_task")
def start_localize_task(project_id: str, config: dict = None, **kwargs):
    action = None
    job = None
    try:
        action = CreativeTaskAction(project_id)

        if not action.project.narration_script_file:
            raise ValueError("母本解说词不存在")

        blueprint_path = action.ensure_blueprint_uploaded()
        master_script_path = action.upload_file_field(action.project.narration_script_file)

        job = action.create_job(CreativeJob.TYPE.LOCALIZE_NARRATION, config)
        action.update_project_status(CreativeProject.Status.LOCALIZATION_RUNNING)

        payload = PayloadBuilder.build_localize_payload(
            master_path=master_script_path, blueprint_path=blueprint_path, raw_config=config
        )
        logger.info(f"[LocalizeTask] Payload: \n{json.dumps(payload, ensure_ascii=False)}")

        success, task_data = action.cloud_service.create_task("LOCALIZE_NARRATION", payload)
        if not success:
            raise Exception(task_data.get("message"))

        job.cloud_task_id = task_data["id"]
        job.save()

        poll_cloud_task.delay(
            job_id=job.id,
            cloud_task_id=task_data["id"],
            on_complete_task_name="apps.workflow.creative.tasks.finalize_localize_task",
            on_complete_kwargs={},
        )

    except Exception as e:
        logger.error(f"[LocalizeTask] Failed: {e}", exc_info=True)
        if job:
            job.fail()
            job.save()
        if action:
            action.update_project_status(CreativeProject.Status.FAILED)


@shared_task(name="apps.workflow.creative.tasks.finalize_localize_task")
def finalize_localize_task(job_id: str, cloud_task_data: dict, **kwargs):
    try:
        job = CreativeJob.objects.get(id=job_id)
        action = CreativeTaskAction(str(job.project.id))

        action.handle_callback_download(
            job_id=job_id,
            cloud_data=cloud_task_data,
            target_file_field_name="localized_script_file",
            filename_prefix="localized_script",
        )

        action.update_project_status(CreativeProject.Status.LOCALIZATION_COMPLETED)

        # [核心修复] 自动化触发 Step 2 (配音)
        if action.project.auto_config:
            logger.info("[AutoPilot] 本地化完成，自动启动 Step 2 (配音)...")
            from .tasks import start_audio_task

            # 智能修正：既然刚跑完翻译，配音肯定是用译本
            audio_conf = action.project.auto_config.get("audio", {}).copy()
            if not audio_conf.get("source_script_type"):
                audio_conf["source_script_type"] = "localized"

            start_audio_task.delay(project_id=str(job.project.id), config=audio_conf)

    except Exception as e:
        logger.error(f"[LocalizeFinal] Failed: {e}", exc_info=True)


# ==============================================================================
# 3. 配音 (Dubbing - Step 2)
# ==============================================================================


@shared_task(name="apps.workflow.creative.tasks.start_audio_task")
def start_audio_task(project_id: str, config: dict = None, **kwargs):
    action = None
    job = None
    try:
        action = CreativeTaskAction(project_id)
        if not config:
            config = {}

        source_type = config.get("source_script_type", "master")
        source_field = (
            action.project.localized_script_file if source_type == "localized" else action.project.narration_script_file
        )

        if not source_field:
            raise ValueError(f"选定的配音脚本源 ({source_type}) 文件不存在")

        input_path = action.upload_file_field(source_field)

        job = action.create_job(CreativeJob.TYPE.GENERATE_AUDIO, config)
        action.update_project_status(CreativeProject.Status.AUDIO_RUNNING)

        payload = PayloadBuilder.build_dubbing_payload(input_path=input_path, raw_config=config)
        logger.info(f"[AudioTask] Payload: \n{json.dumps(payload, ensure_ascii=False)}")

        success, task_data = action.cloud_service.create_task("GENERATE_DUBBING", payload)
        if not success:
            raise Exception(task_data.get("message"))

        job.cloud_task_id = task_data["id"]
        job.save()

        poll_cloud_task.delay(
            job_id=job.id,
            cloud_task_id=task_data["id"],
            on_complete_task_name="apps.workflow.creative.tasks.finalize_audio_task",
            on_complete_kwargs={},
        )

    except Exception as e:
        logger.error(f"[AudioTask] Failed: {e}", exc_info=True)
        if job:
            job.fail()
            job.save()
        if action:
            action.update_project_status(CreativeProject.Status.FAILED)


@shared_task(name="apps.workflow.creative.tasks.finalize_audio_task")
def finalize_audio_task(job_id: str, cloud_task_data: dict, **kwargs):
    """
    [Callback] 配音回调。
    """
    try:
        job = CreativeJob.objects.get(id=job_id)
        action = CreativeTaskAction(str(job.project.id))

        # 1. 下载脚本
        action.handle_callback_download(
            job_id=job_id,
            cloud_data=cloud_task_data,
            target_file_field_name="dubbing_script_file",
            filename_prefix="dubbing_script",
        )

        # 2. 下载音频资源
        action.download_assets_from_dubbing_script(job_id)

        action.update_project_status(CreativeProject.Status.AUDIO_COMPLETED)

        # 3. 触发 Step 3 (剪辑脚本)
        if action.project.auto_config:
            logger.info("[AutoPilot] 配音完成，自动启动 Step 3 (剪辑脚本)...")
            from .tasks import start_edit_script_task

            start_edit_script_task.delay(project_id=str(action.project.id))

    except Exception as e:
        logger.error(f"[AudioFinal] Failed: {e}", exc_info=True)


# ==============================================================================
# 4. 生成剪辑脚本 (Edit Script - Step 3)
# ==============================================================================


@shared_task(name="apps.workflow.creative.tasks.start_edit_script_task")
def start_edit_script_task(project_id: str, **kwargs):
    action = None
    job = None
    try:
        action = CreativeTaskAction(project_id)

        if not action.project.dubbing_script_file:
            raise ValueError("配音脚本 (Dubbing Script) 不存在，无法生成剪辑脚本。请先完成步骤 2。")

        blueprint_path = action.ensure_blueprint_uploaded()
        dubbing_script_path = action.upload_file_field(action.project.dubbing_script_file)

        job = action.create_job(CreativeJob.TYPE.GENERATE_EDIT_SCRIPT, {})
        action.update_project_status(CreativeProject.Status.EDIT_RUNNING)

        payload = {
            "dubbing_script_path": dubbing_script_path,
            "blueprint_path": blueprint_path,
            "service_params": {"lang": "zh"},
        }
        logger.info(f"[EditTask] Payload: {json.dumps(payload, ensure_ascii=False)}")

        success, task_data = action.cloud_service.create_task("GENERATE_EDITING_SCRIPT", payload)
        if not success:
            raise Exception(task_data.get("message"))

        job.cloud_task_id = task_data["id"]
        job.save()

        poll_cloud_task.delay(
            job_id=job.id,
            cloud_task_id=task_data["id"],
            on_complete_task_name="apps.workflow.creative.tasks.finalize_edit_script_task",
            on_complete_kwargs={},
        )

    except Exception as e:
        logger.error(f"[EditTask] Failed: {e}", exc_info=True)
        if job:
            job.fail()
            job.save()
        if action:
            action.update_project_status(CreativeProject.Status.FAILED)


@shared_task(name="apps.workflow.creative.tasks.finalize_edit_script_task")
def finalize_edit_script_task(job_id: str, cloud_task_data: dict, **kwargs):
    try:
        job = CreativeJob.objects.get(id=job_id)
        action = CreativeTaskAction(str(job.project.id))

        action.handle_callback_download(
            job_id=job_id,
            cloud_data=cloud_task_data,
            target_file_field_name="edit_script_file",
            filename_prefix="editing_script",
        )

        action.update_project_status(CreativeProject.Status.EDIT_COMPLETED)

        # 触发 Step 4 (合成)
        if action.project.auto_config:
            logger.info("[AutoPilot] 剪辑脚本完成，自动启动 Step 4 (最终合成)...")
            start_synthesis_task.delay(project_id=str(action.project.id))

    except Exception as e:
        logger.error(f"[EditFinal] Failed: {e}", exc_info=True)


# ==============================================================================
# 5. 视频合成 (Synthesis - Step 4)
# ==============================================================================


@shared_task(name="apps.workflow.creative.tasks.start_synthesis_task")
def start_synthesis_task(project_id: str, **kwargs):
    action = None
    job = None
    try:
        action = CreativeTaskAction(project_id)

        if action.project.status == CreativeProject.Status.SYNTHESIS_RUNNING:
            logger.warning(f"项目 {project_id} 正在合成中，跳过重复触发。")
            return

        job = action.create_job(CreativeJob.TYPE.SYNTHESIS, {})
        action.update_project_status(CreativeProject.Status.SYNTHESIS_RUNNING)

        if not action.project.edit_script_file:
            raise ValueError("缺少剪辑脚本 (edit_script_file)")
        editing_script_path = Path(action.project.edit_script_file.path)

        inf_proj = action.project.inference_project
        if not inf_proj.annotation_project.final_blueprint_file:
            raise ValueError("缺少叙事蓝图 (final_blueprint_file)")
        blueprint_path = Path(inf_proj.annotation_project.final_blueprint_file.path)

        source_videos_dir = Path(settings.MEDIA_ROOT) / "source_files" / str(action.project.asset.id) / "media"

        # [修正] 查找最近一个成功的 Audio 任务
        last_audio_job = (
            CreativeJob.objects.filter(
                project=action.project,
                job_type=CreativeJob.TYPE.GENERATE_AUDIO,
                status="COMPLETED",  # 确保引用 BaseJob.STATUS 的值，通常是 "COMPLETED"
            )
            .order_by("-modified")
            .first()
        )

        if not last_audio_job:
            raise ValueError("找不到已完成的配音任务，无法定位音频文件。")

        relative_audio_dir = f"creative/{action.project.id}/outputs/audio_{last_audio_job.id}"
        local_audio_base_dir = Path(settings.MEDIA_ROOT) / relative_audio_dir

        if not local_audio_base_dir.exists():
            raise FileNotFoundError(f"音频目录不存在: {local_audio_base_dir}")

        logger.info(f"[Synthesis] 准备就绪。AudioDir: {local_audio_base_dir}")

        service = SynthesisService(project_id)

        final_output_path = service.execute(
            editing_script_path=editing_script_path,
            blueprint_path=blueprint_path,
            local_audio_base_dir=local_audio_base_dir,
            source_videos_dir=source_videos_dir,
            asset_id=str(action.project.asset.id),
        )

        finalize_synthesis_task(job_id=str(job.id), final_output_path=str(final_output_path))

    except Exception as e:
        logger.error(f"[Synthesis] Failed: {e}", exc_info=True)
        if job:
            job.fail()
            job.save()
        if action:
            action.update_project_status(CreativeProject.Status.FAILED)


@shared_task(name="apps.workflow.creative.tasks.finalize_synthesis_task")
def finalize_synthesis_task(job_id: str, final_output_path: str, **kwargs):
    try:
        job = CreativeJob.objects.get(id=job_id)
        project = job.project

        output_path_obj = Path(final_output_path)
        if not output_path_obj.exists():
            raise FileNotFoundError(f"合成产物未找到: {final_output_path}")

        with output_path_obj.open("rb") as f:
            project.final_video_file.save(output_path_obj.name, ContentFile(f.read()), save=False)

        project.status = CreativeProject.Status.COMPLETED
        project.save()

        job.complete()
        job.save()

        logger.info(f"[SynthesisFinal] 视频合成全流程结束！Project: {project.id}")

    except Exception as e:
        logger.error(f"[SynthesisFinal] Failed: {e}", exc_info=True)
