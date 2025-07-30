# 文件路径: apps/media_assets/tasks.py
import json
import os
import shutil
import subprocess
import threading
import boto3
import requests
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError

from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile
from pathlib import Path
from .services.modeling.script_modeler import ScriptModeler

class ProgressLogger:
    def __init__(self, filename):
        self._filename = filename
        self._size = float(os.path.getsize(filename))
        self._seen_so_far = 0
        self._lock = threading.Lock()

    def __call__(self, bytes_amount):
        # boto3 会在多线程中调用这个回调，所以我们需要加锁来保证打印的线程安全
        with self._lock:
            self._seen_so_far += bytes_amount
            percentage = (self._seen_so_far / self._size) * 100
            print(f"上传进度: {self._filename}  {self._seen_so_far} / {int(self._size)} bytes ({percentage:.2f}%)")

@shared_task
def process_media_asset(asset_id):
    """
    处理媒资文件的异步任务：
    1. 使用 FFmpeg 降低视频码率
    2. 将处理后的视频和原始 SRT 上传到 AWS S3
    3. 将两个文件的公开 URL 写回数据库
    """
    asset = None
    source_video_path = None
    processed_video_path = None
    source_srt_path = None

    try:
        from apps.media_assets.models import Asset
        asset = Asset.objects.get(id=asset_id)

        # --- 1. 状态更新与文件定位 ---
        if not asset.source_video or not hasattr(asset.source_video, 'path'):
            raise FileNotFoundError(f"Asset (ID: {asset_id}) 的源视频文件不存在。")

        source_video_path = asset.source_video.path
        if asset.source_subtitle and hasattr(asset.source_subtitle, 'path'):
            source_srt_path = asset.source_subtitle.path

        asset.processing_status = 'processing'
        asset.save(update_fields=['processing_status'])

        # --- 2. FFmpeg 视频处理 ---
        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_processed')
        os.makedirs(temp_dir, exist_ok=True)
        processed_filename = f"{asset.id}.mp4"
        processed_video_path = os.path.join(temp_dir, processed_filename)

        ffmpeg_command = ['ffmpeg', '-i', source_video_path, '-c:v', 'libx264', '-b:v', '2M', '-preset', 'fast', '-y',
                          processed_video_path]
        print(f"执行 FFmpeg 命令: {' '.join(ffmpeg_command)}")
        subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True)
        print("FFmpeg 处理成功！")

        # --- 3. 上传文件到 AWS S3 ---
        print("开始上传文件到 S3...")
        s3_client = boto3.client('s3', region_name=settings.AWS_S3_REGION_NAME)

        # 上传处理后的视频
        video_s3_key = f"processed_videos/{processed_filename}"
        video_progress = ProgressLogger(processed_video_path)
        s3_client.upload_file(processed_video_path, settings.AWS_STORAGE_BUCKET_NAME, video_s3_key,Callback=video_progress)
        video_cdn_url = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{video_s3_key}"
        print(f"视频已上传, URL: {video_cdn_url}")

        # 如果有字幕文件，也上传它，并获取其 URL
        srt_cdn_url = None
        if source_srt_path:
            srt_filename = os.path.basename(source_srt_path)
            srt_s3_key = f"source_subtitles/{asset.id}/{srt_filename}"
            srt_progress = ProgressLogger(source_srt_path)
            s3_client.upload_file(source_srt_path, settings.AWS_STORAGE_BUCKET_NAME, srt_s3_key,Callback=srt_progress)
            srt_cdn_url = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{srt_s3_key}"
            print(f"字幕已上传, URL: {srt_cdn_url}")

        # --- 4. 将所有结果一次性写回数据库 ---
        asset.processing_status = 'completed'
        asset.processed_video_url = video_cdn_url
        asset.source_subtitle_url = srt_cdn_url  # <-- 关键的同步步骤
        asset.save(update_fields=['processing_status', 'processed_video_url', 'source_subtitle_url'])

        print(f"处理完成 Asset: {asset.title}")
        return f"Asset {asset_id} processed and uploaded successfully."

    except (NoCredentialsError, PartialCredentialsError):
        print("S3 凭证配置不正确或缺失！")
        if asset:
            asset.processing_status = 'failed'
            asset.save(update_fields=['processing_status'])
        raise
    except ClientError as e:
        print(f"S3 上传时发生客户端错误: {e}")
        if asset:
            asset.processing_status = 'failed'
            asset.save(update_fields=['processing_status'])
        raise
    except Exception as e:
        print(f"处理 Asset {asset_id} 时发生未知错误: {e}")
        if asset:
            asset.processing_status = 'failed'
            asset.save(update_fields=['processing_status'])
        raise
    finally:
        # --- 5. 清理本地临时文件 ---
        if source_video_path and os.path.exists(source_video_path):
            os.remove(source_video_path)
        if processed_video_path and os.path.exists(processed_video_path):
            os.remove(processed_video_path)
        # 注意：源SRT文件如果还需要用于第一层标注，可以考虑不在这里删除
        # if source_srt_path and os.path.exists(source_srt_path):
        #     os.remove(source_srt_path)
        print("临时文件清理完毕。")

@shared_task
def export_data_from_ls(media_id):
    """
    (重构版) 从 Label Studio 导出整个项目的标注数据，并保存到 Media 对象。
    """
    from .models import Media  # <-- 注意：现在导入的是 Media 模型

    media = None
    try:
        media = Media.objects.get(id=media_id)
        if not media.label_studio_project_id:
            print(f"错误: Media {media.id} 缺少 LS Project ID，无法导出。")
            return f"Export failed: Media {media.id} is missing LS project ID."

        project_id = media.label_studio_project_id
        print(f"开始从 LS 导出 Project {project_id} 的全部数据...")

        label_studio_url = settings.LABEL_STUDIO_URL
        api_token = settings.LABEL_STUDIO_ACCESS_TOKEN
        headers = {"Authorization": f"Token {api_token}"}

        # 调用获取整个项目导出的 API
        export_url = f"{label_studio_url}/api/projects/{project_id}/export"

        # LS 的导出 API 可能会需要一些时间生成，通常会先返回一个任务 ID
        # 但对于中小型项目，它也可能直接返回文件。我们先按直接返回文件处理。
        # 增加 stream=True 以便处理可能的大文件
        response = requests.get(export_url, headers=headers, stream=True)
        response.raise_for_status()

        # 将返回的文件流内容保存到 label_studio_export_file 字段
        file_name = f"ls_export_project_{project_id}.json"

        # 使用 Django 的 ContentFile 来包装二进制内容
        # response.content 会将整个文件读入内存，对于大文件有风险
        # 更稳健的方式是分块写入，这里为了简化先用 .content
        file_content = response.content

        media.label_studio_export_file.save(file_name, ContentFile(file_content), save=True)

        print(f"成功导出并保存了 Project {project_id} 的标注数据到 {media.label_studio_export_file.name}")

        # （可选）更新 Media 的状态
        # media.blueprint_status = 'ready_for_modeling'
        # media.save()

        return f"Export successful for Media {media.id}"


    except Media.DoesNotExist:
        print(f"错误：在导出任务中找不到 ID 为 {media_id} 的 Media。")
        return f"Export failed: Media with id {media_id} not found."
    except requests.exceptions.RequestException as e:
        print(f"从 LS 导出数据时 API 请求失败: {e}")
        if media:
            media.l2_l3_status = 'pending'  # 状态可以回滚为 pending
            media.save()
        raise
    except Exception as e:
        print(f"导出 LS 数据时发生未知错误: {e}")
        if media:
            media.l2_l3_status = 'pending'
            media.save()
        raise

@shared_task
def generate_narrative_blueprint(media_id):
    """
    一个包装器任务，负责调用 ScriptModeler 引擎来生成最终的叙事蓝图。
    """
    from .models import Media

    print(f"开始为 Media ID: {media_id} 生成叙事蓝图...")
    media = Media.objects.get(id=media_id)

    try:
        # --- 1. 准备 ScriptModeler 所需的输入 ---

        # a. 准备 Label Studio JSON 导出文件
        # 注意：ScriptModeler 需要一个聚合的 JSON，而我们是按 Asset (Task) 导出的。
        # 我们需要先将多个 Task 的标注数据合并成 LS 导出的那种列表格式。
        all_annotations = []
        for asset in media.assets.order_by('sequence_number'):
            if asset.l2_l3_output_file and hasattr(asset.l2_l3_output_file, 'path'):
                with open(asset.l2_l3_output_file.path, 'r', encoding='utf-8') as f:
                    # l2_l3_output_file 存储的是单个 task 的数据
                    # 我们需要把它模拟成 LS 导出的那种包含 "annotations" 的结构
                    task_data = json.load(f)
                    all_annotations.append(task_data)  # [FIX] 简化为直接聚合任务数据
            else:
                print(f"警告: Asset {asset.id} 缺少 L2/L3 标注文件，跳过。")

        # 将聚合后的数据写入一个临时的 JSON 文件
        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_modeler_inputs')
        os.makedirs(temp_dir, exist_ok=True)
        aggregated_ls_json_path = Path(temp_dir) / f"{media.id}_ls_export.json"
        with open(aggregated_ls_json_path, 'w', encoding='utf-8') as f:
            json.dump(all_annotations, f)

        # b. 准备 ASS 文件所在的目录
        # 我们将所有相关的 .ass 文件复制到一个临时目录中
        ass_dir_path = Path(temp_dir) / f"{media.id}_ass_files"
        os.makedirs(ass_dir_path, exist_ok=True)
        for i, asset in enumerate(media.assets.order_by('sequence_number')):
            if asset.l1_output_file and hasattr(asset.l1_output_file, 'path'):
                # ScriptModeler 期望 ass 文件名为 01.ass, 02.ass ...
                target_ass_name = f"{i + 1:02d}.ass"
                shutil.copy(asset.l1_output_file.path, ass_dir_path / target_ass_name)

        # --- 2. 实例化并运行 ScriptModeler ---
        modeler = ScriptModeler(ls_json_path=aggregated_ls_json_path, ass_dir_path=ass_dir_path)
        final_structured_script = modeler.build()

        # --- 3. 将产出物保存回数据库 ---
        media.final_narrative_asset = final_structured_script
        media.save(update_fields=['final_narrative_asset'])

        print(f"成功为 Media ID: {media_id} 生成并保存了叙事蓝图！")

        # --- 4. 清理临时文件 ---
        shutil.rmtree(temp_dir)
        print("已清理临时文件。")

        return f"Blueprint generated successfully for Media {media_id}"

    except Exception as e:
        print(f"为 Media ID: {media_id} 生成叙事蓝图时发生错误: {e}")
        raise

@shared_task
def ingest_media_files(media_id):
    """
    (新) 核心编排任务：
    1. 扫描指定目录的文件
    2. 自动创建 Asset 记录
    3. 为每个 Asset 执行文件处理（转码+存储）
    """
    from .models import Media, Asset

    media = None
    try:
        media = Media.objects.get(id=media_id)
        media.ingestion_status = 'ingesting'
        media.save()

        # 定义一个用于批量上传的“接收”目录
        upload_dir = Path(settings.MEDIA_ROOT) / 'batch_uploads' / str(media.id)
        if not upload_dir.exists():
            print(f"警告：未找到 Media ID: {media_id} 的上传目录: {upload_dir}")
            media.ingestion_status = 'failed'
            media.save()
            return f"Ingestion failed: Upload directory not found for Media {media.id}"

        # 扫描目录中的视频文件
        video_files = list(upload_dir.glob('*.mp4')) + list(upload_dir.glob('*.mov'))
        print(f"在 {upload_dir} 中找到 {len(video_files)} 个视频文件。")

        for video_path in video_files:
            # --- a. 自动创建 Asset ---
            base_name = video_path.stem
            srt_path = upload_dir / f"{base_name}.srt"

            # 假设 sequence_number 来自文件名，例如 ep01 -> 1
            sequence_number = int("".join(filter(str.isdigit, base_name)) or 0)

            asset, created = Asset.objects.get_or_create(
                media=media,
                sequence_number=sequence_number,
                defaults={'title': base_name}
            )
            print(f"已创建/找到 Asset: {asset.title}")

            # --- b. 执行文件处理 ---
            asset.processing_status = 'processing'
            asset.save()

            # i. 视频转码 (FFmpeg)
            temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_processed')
            os.makedirs(temp_dir, exist_ok=True)
            processed_filename = f"{asset.id}.mp4"
            processed_video_path = os.path.join(temp_dir, processed_filename)
            ffmpeg_command = ['ffmpeg', '-i', str(video_path), '-c:v', 'libx264', '-b:v', '2M', '-preset', 'fast', '-y',
                              processed_video_path]
            subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True)
            print(f"FFmpeg 处理成功 for Asset {asset.id}")

            # ii. 存储后端决策
            video_url = None
            srt_url = None

            if settings.STORAGE_BACKEND == 's3':
                s3_client = boto3.client('s3', region_name=settings.AWS_S3_REGION_NAME)
                # 上传视频
                video_s3_key = f"processed_videos/{processed_filename}"
                s3_client.upload_file(processed_video_path, settings.AWS_STORAGE_BUCKET_NAME, video_s3_key)
                video_url = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{video_s3_key}"
                # 上传SRT
                if srt_path.exists():
                    srt_s3_key = f"source_subtitles/{asset.id}/{srt_path.name}"
                    s3_client.upload_file(str(srt_path), settings.AWS_STORAGE_BUCKET_NAME, srt_s3_key)
                    srt_url = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{srt_s3_key}"
            else:  # Local Nginx 模式
                nginx_dir = "/app/media_root/processed_files"
                os.makedirs(nginx_dir, exist_ok=True)
                # 移动视频
                shutil.move(processed_video_path, os.path.join(nginx_dir, processed_filename))
                video_url = f"{settings.LOCAL_MEDIA_URL_BASE}/media/{processed_filename}"
                # 复制SRT
                if srt_path.exists():
                    shutil.copy(str(srt_path), os.path.join(nginx_dir, srt_path.name))
                    srt_url = f"{settings.LOCAL_MEDIA_URL_BASE}/media/{srt_path.name}"

            # iii. 回写 Asset 记录
            asset.processed_video_url = video_url
            asset.source_subtitle_url = srt_url
            asset.processing_status = 'completed'
            asset.save()
            print(f"文件处理和存储完成 for Asset {asset.id}")

        # --- 最终化 ---
        media.ingestion_status = 'completed'
        media.save()
        print(f"Media ID: {media_id} 的所有文件已加载处理完毕。")
        return f"Ingestion complete for Media {media_id}"

    except Exception as e:
        print(f"为 Media ID: {media_id} 批量加载文件时发生错误: {e}")
        if media:
            media.ingestion_status = 'failed'
            media.save()
        raise