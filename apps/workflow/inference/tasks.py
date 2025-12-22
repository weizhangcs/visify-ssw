# 文件路径: apps/workflow/inference/tasks.py

import json
import logging
from pathlib import Path

from celery import shared_task
from django.core.files.base import ContentFile

from apps.workflow.common.baseJob import BaseJob

# 导入 Celery App 实例，用于链式调用
from visify_ssw.celery import app as celery_app

from .projects import InferenceJob
from .services.cloud_api import CloudApiService

# 注意：CreativeJob 将在函数内部动态导入以避免循环引用


logger = logging.getLogger(__name__)


@shared_task(
    bind=True, name="apps.workflow.inference.tasks.poll_cloud_task_status", max_retries=50, default_retry_delay=30
)
def poll_cloud_task_status(self, job_id: str, cloud_task_id: int, on_complete_task_name: str, on_complete_kwargs: dict):
    """
    (已重构 V3.2 - 智能兼容版)
    通用的云端任务轮询器。
    现在可以根据回调任务名称，智能判断是 InferenceJob 还是 CreativeJob。
    """
    # 动态导入 CreativeJob 以避免循环依赖
    from apps.workflow.creative.jobs import CreativeJob
    from apps.workflow.inference.projects import InferenceJob

    job = None
    job_type_label = "Unknown"

    try:
        # --- 核心修复：智能路由逻辑 ---
        # 如果回调任务属于 creative 应用，则去查 CreativeJob
        if "apps.workflow.creative" in on_complete_task_name:
            job_type_label = "CreativeJob"
            job = CreativeJob.objects.get(id=job_id)
        else:
            # 否则默认为 InferenceJob
            job_type_label = "InferenceJob"
            job = InferenceJob.objects.get(id=job_id)

    except (InferenceJob.DoesNotExist, CreativeJob.DoesNotExist):
        logger.error(f"[PollTask] 找不到 {job_type_label} (ID: {job_id})，轮询任务终止。")
        return

    logger.info(f"[PollTask] 正在查询 {job_type_label} {job_id} 的云端任务 {cloud_task_id} 状态...")

    try:
        service = CloudApiService()
        success, data = service.get_task_status(cloud_task_id)
    except Exception:
        logger.error(f"[PollTask] API查询失败 (Job: {job_id})，将在 {self.default_retry_delay} 秒后重试。", exc_info=True)
        self.retry()  # 仅在API/网络错误时重试
        return

    if not success:
        logger.warning(f"[PollTask] 查询云端任务 {cloud_task_id} 失败 (Job: {job_id})，将在 {self.default_retry_delay} 秒后重试。")
        self.retry()
        return

    status = data.get("status")

    if status == "COMPLETED":
        logger.info(f"[PollTask] 云端任务 {cloud_task_id} (Job: {job_id}) 已完成。触发后续任务: {on_complete_task_name}")
        celery_app.send_task(
            on_complete_task_name, kwargs={"job_id": job_id, "cloud_task_data": data, **on_complete_kwargs}
        )

    elif status in ["PENDING", "RUNNING"]:
        # 成功的查询，但任务未完成，进入下一次重试。
        logger.info(
            f"[PollTask] 云端任务 {cloud_task_id} (Job: {job_id}) 仍在 {status} 状态，将在 {self.default_retry_delay} 秒后重试。"
        )
        self.retry()  # 再次发起重试，程序会在此处停止并抛出 Retry 异常。

    elif status == "FAILED":
        logger.error(f"[PollTask] 云端任务 {cloud_task_id} (Job: {job_id}) 报告失败。")
        job.fail()
        job.save()

    else:
        logger.error(f"[PollTask] 云端任务 {cloud_task_id} (Job: {job_id}) 返回未知状态: '{status}'。")
        job.fail()
        job.save()


@shared_task(name="apps.workflow.inference.tasks.start_rag_deployment_task")
def start_rag_deployment_task(job_id: str, **kwargs):
    """
    (保持不变) 启动 RAG 部署任务
    """
    job = None
    try:
        job = InferenceJob.objects.get(id=job_id)
        project = job.project

        job.start()  # PENDING -> PROCESSING
        job.save()

    except InferenceJob.DoesNotExist:
        logger.error(f"[RAGDeploy] 找不到 InferenceJob {job_id}，任务终止。")
        return
    except Exception as e:
        logger.error(f"[RAGDeploy] 无法将 Job {job_id} 设为 PROCESSING: {e}", exc_info=True)
        return

    try:
        # 1. 从 input_params 获取源 Job ID
        source_facts_job_id = job.input_params.get("source_facts_job_id")
        if not source_facts_job_id:
            raise ValueError("input_params 中缺少 'source_facts_job_id'。")

        source_job = InferenceJob.objects.get(id=source_facts_job_id, status=BaseJob.STATUS.COMPLETED)

        if not source_job.cloud_blueprint_path:
            raise ValueError(f"源 Job {source_facts_job_id} 缺少 'cloud_blueprint_path'。")
        if not source_job.cloud_facts_path:
            raise ValueError(f"源 Job {source_facts_job_id} 缺少 'cloud_facts_path'。")

        logger.info(f"[RAGDeploy] Job {job_id} 正在启动 RAG 部署...")

        # 2. 将路径保存到 *这个* Job
        job.cloud_blueprint_path = source_job.cloud_blueprint_path
        job.cloud_facts_path = source_job.cloud_facts_path

        service = CloudApiService()

        # 3. 创建 DEPLOY_RAG_CORPUS 任务
        payload = {
            "blueprint_input_path": job.cloud_blueprint_path,
            "facts_input_path": job.cloud_facts_path,
            "asset_id": str(project.asset.id),
        }
        success, task_data = service.create_task("DEPLOY_RAG_CORPUS", payload)
        if not success:
            raise Exception(task_data.get("message", "Failed to create DEPLOY_RAG_CORPUS task"))

        job.cloud_task_id = task_data["id"]
        job.save()

        # 4. 触发轮询
        poll_cloud_task_status.delay(
            job_id=job_id,
            cloud_task_id=task_data["id"],
            on_complete_task_name="apps.workflow.inference.tasks.finalize_rag_deployment",
            on_complete_kwargs={},
        )
    except Exception as e:
        logger.error(f"[RAGDeploy] Job {job_id} 失败: {e}", exc_info=True)
        if job:
            job.fail()
            job.save()


@shared_task(name="apps.workflow.inference.tasks.finalize_rag_deployment")
def finalize_rag_deployment(job_id: str, cloud_task_data: dict, **kwargs):
    """
    (已重构 V3.2 - 幂等性修复版)
    RAG 部署任务成功后的回调。
    """
    job = None
    try:
        job = InferenceJob.objects.get(id=job_id)

        # --- [修复 1: 幂等性检查] ---
        # 如果任务已经完成，直接退出，防止 TransitionNotAllowed 错误
        if job.status == BaseJob.STATUS.COMPLETED:
            logger.warning(f"[RAGFinal] Job {job_id} 状态已是 COMPLETED，跳过重复执行。")
            return

        project = job.project
    except InferenceJob.DoesNotExist:
        logger.error(f"[RAGFinal] 找不到 InferenceJob {job_id}，任务终止。")
        return

    try:
        service = CloudApiService()
        download_url = cloud_task_data.get("download_url")
        total_scene_count = None

        if download_url:
            # 2. 下载结果文件 (保持与上次修复一致的完整逻辑)
            success, content = service.download_task_result(download_url)

            if success:
                # 3. 保存文件到 Job
                job.output_rag_report_file.save(f"rag_report_{job_id}.json", ContentFile(content), save=False)

                # 4. 解析 JSON 并提取字段
                try:
                    report_data = json.loads(content.decode("utf-8"))
                    total_scene_count = report_data.get("total_scene_count")

                    if total_scene_count is not None:
                        project.rag_total_scene_count = total_scene_count
                        logger.info(f"[RAGFinal] 策略2命中: 从下载的文件中获取到 count: {total_scene_count}")
                    else:
                        logger.warning("[RAGFinal] 文件下载成功，但 JSON 中缺少 total_scene_count 字段。")

                except json.JSONDecodeError:
                    logger.error("[RAGFinal] 下载的文件不是有效的 JSON，无法提取字段。")
            else:
                logger.warning(f"[RAGFinal] 任务已完成，但下载 RAG 报告失败: {download_url}")
        else:
            logger.warning("[RAGFinal] 云端任务完成但未提供 download_url。")

        # 5. 尝试从 'result' 直接获取 (双重保险)
        if total_scene_count is None:
            result_data = cloud_task_data.get("result", {})
            if isinstance(result_data, dict) and result_data.get("total_scene_count"):
                project.rag_total_scene_count = result_data.get("total_scene_count")
                total_scene_count = project.rag_total_scene_count  # 确保 total_scene_count 变量被更新
                logger.info(f"[RAGFinal] 从 API result 直接提取到 total_scene_count: {project.rag_total_scene_count}")

        # 6. 保存 Project 和 Job 状态
        project.save(update_fields=["rag_total_scene_count"])

        job.complete()
        job.save()

        logger.info(f"[RAGFinal] Job {job_id} (项目 {project.id}) 的云端推理工作流已全部完成！")

    except Exception as e:
        logger.error(f"[RAGFinal] Job {job_id} 最终化处理失败: {e}", exc_info=True)
        if job:
            job.fail()
            job.save()


@shared_task(name="apps.workflow.inference.tasks.start_cloud_facts_task")
def start_cloud_facts_task(job_id: str, **kwargs):
    """
    (保持不变) 启动 FACTS 任务
    """
    job = None
    try:
        job = InferenceJob.objects.get(id=job_id)
        project = job.project
        annotation_project = project.annotation_project

        job.start()
        job.save()
    except InferenceJob.DoesNotExist:
        logger.error(f"[FactsTask] 找不到 InferenceJob {job_id}，任务终止。")
        return
    except Exception as e:
        logger.error(f"[FactsTask] 无法将 Job {job_id} 设为 PROCESSING: {e}", exc_info=True)
        return

    try:
        if not annotation_project.final_blueprint_file:
            raise ValueError(f"关联的 AnnotationProject {annotation_project.id} 缺少 'final_blueprint_file'。")

        characters_to_analyze = job.input_params.get("characters")
        if not characters_to_analyze:
            raise ValueError("input_params 中缺少 'characters'。")

        logger.info(f"[FactsTask] Job {job_id} 正在启动 FACTS 识别...")
        service = CloudApiService()

        logger.info(f"[FactsTask] 正在上传蓝图 {annotation_project.final_blueprint_file.name}...")
        success, blueprint_path = service.upload_file(Path(annotation_project.final_blueprint_file.path))
        if not success:
            raise Exception(f"蓝图上传失败: {blueprint_path}")

        job.cloud_blueprint_path = blueprint_path

        payload = {
            "input_file_path": job.cloud_blueprint_path,
            "service_params": {
                "characters_to_analyze": characters_to_analyze,
                "lang": annotation_project.asset.language.split("-")[0] if annotation_project.asset.language else "zh",
                "model": "gemini-2.5-flash",
                "temp": 0.1,
            },
        }
        success, task_data = service.create_task("CHARACTER_IDENTIFIER", payload)
        if not success:
            raise Exception(task_data.get("message", "Failed to create CHARACTER_IDENTIFIER task"))

        job.cloud_task_id = task_data["id"]
        job.save(update_fields=["cloud_blueprint_path", "cloud_task_id", "status"])

        poll_cloud_task_status.delay(
            job_id=job_id,
            cloud_task_id=task_data["id"],
            on_complete_task_name="apps.workflow.inference.tasks.finalize_facts_task",
            on_complete_kwargs={},
        )
    except Exception as e:
        logger.error(f"[FactsTask] Job {job_id} 失败: {e}", exc_info=True)
        if job:
            job.fail()
            job.save()


@shared_task(name="apps.workflow.inference.tasks.finalize_facts_task")
def finalize_facts_task(job_id: str, cloud_task_data: dict, **kwargs):
    """
    (保持不变) FACTS 任务回调
    """
    job = None
    try:
        job = InferenceJob.objects.get(id=job_id)
        project = job.project  # 获取 Project 实例
    except InferenceJob.DoesNotExist:
        logger.error(f"[FactsFinal] 找不到 InferenceJob {job_id}，任务终止。")
        return

    try:
        facts_path = cloud_task_data.get("result", {}).get("output_file_path")
        if facts_path:
            job.cloud_facts_path = facts_path

        service = CloudApiService()
        download_url = cloud_task_data.get("download_url")
        if download_url:
            success, content = service.download_task_result(download_url)
            if success:
                job.output_facts_file.save(f"facts_result_{job_id}.json", ContentFile(content), save=False)
            else:
                logger.warning(f"[FactsFinal] 任务已完成，但下载 facts_result_file 失败: {download_url}")

        job.complete()
        job.save()

        logger.info(f"[FactsFinal] Job {job_id} (项目 {job.project.id}) 的角色属性识别已完成！")
        # --- [核心修复：链式触发 RAG 部署任务] ---

        # 1. 查找或创建 RAG 部署 Job
        # Note: 此时 start_rag_deployment_task 已经被 Celery 识别，可以直接调用

        # 查找最新的 RAG Job 实例，避免重复创建
        latest_rag_job = (
            InferenceJob.objects.filter(project=project, job_type=InferenceJob.TYPE.RAG_DEPLOYMENT)
            .order_by("-created")
            .first()
        )

        if latest_rag_job and latest_rag_job.status in [BaseJob.STATUS.PENDING, BaseJob.STATUS.FAILED]:
            # 重用或重试 Job
            new_rag_job = latest_rag_job
            logger.info(f"[FactsFinal] 重用并重置 RAG 任务 {new_rag_job.id}")
        else:
            # 创建一个新的 RAG 部署 Job
            new_rag_job = InferenceJob.objects.create(
                project=project,
                job_type=InferenceJob.TYPE.RAG_DEPLOYMENT,
                status=BaseJob.STATUS.PENDING,
            )

        # 2. 注入输入参数
        new_rag_job.input_params = {"source_facts_job_id": str(job.id)}
        new_rag_job.save()

        # 3. 触发 RAG 任务 (直接使用函数名，Python 在加载完所有函数后可以识别)
        logger.info(f"[FactsFinal] 触发 RAG 部署任务 {new_rag_job.id} (源 Job: {job.id})...")
        start_rag_deployment_task.delay(job_id=str(new_rag_job.id))

    except Exception as e:
        logger.error(f"[FactsFinal] Job {job_id} 最终化处理失败: {e}", exc_info=True)
        if job:
            job.fail()
            job.save()
