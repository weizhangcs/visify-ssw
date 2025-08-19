# 文件路径: apps/media_assets/tasks.py
import json
import os
import shutil
import subprocess
import threading
import re
from datetime import datetime, timezone
from collections import defaultdict

import boto3
import requests
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError
import csv
from io import StringIO
from collections import defaultdict
from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files import File
from pathlib import Path
from .services.modeling.script_modeler import ScriptModeler
from .services.storage import StorageService
import logging

# 获取一个模块级的 logger 实例
logger = logging.getLogger(__name__)


class ProgressLogger:
    def __init__(self, filename):
        self._filename = filename
        self._size = float(os.path.getsize(filename))
        self._seen_so_far = 0
        self._lock = threading.Lock()

    def __call__(self, bytes_amount):
        with self._lock:
            self._seen_so_far += bytes_amount
            percentage = (self._seen_so_far / self._size) * 100
            logger.info(
                f"上传进度: {self._filename}  {self._seen_so_far} / {int(self._size)} bytes ({percentage:.2f}%)")


def _check_and_update_media_processing_status(asset):
    """
    检查给定 asset 所属的 media 下的所有 asset 的处理状态，
    并相应地更新 media 的聚合处理状态。
    """
    media = asset.media
    all_assets = media.assets.all()
    total_assets = all_assets.count()

    if total_assets == 0:
        media.processing_status = 'pending'
        media.save(update_fields=['processing_status'])
        return

    completed_statuses = ['completed', 'updated']

    completed_count = all_assets.filter(processing_status__in=completed_statuses).count()
    failed_count = all_assets.filter(processing_status='failed').count()

    if failed_count > 0:
        media.processing_status = 'failed'
    elif completed_count == total_assets:
        media.processing_status = 'completed'
    else:
        media.processing_status = 'processing'

    media.save(update_fields=['processing_status'])


@shared_task
def process_single_asset_files(asset_id):
    """
    (V3.3) 增加标准日志记录
    """
    from .models import Asset
    asset = Asset.objects.get(id=asset_id)
    storage_service = StorageService()
    original_status = asset.processing_status

    try:
        if not asset.source_video or not hasattr(asset.source_video, 'path'):
            raise FileNotFoundError(f"Asset (ID: {asset.id}) 的源视频在数据库中未记录路径。")

        source_video_path = Path(asset.source_video.path)
        if not source_video_path.is_file():
            logger.critical(f"!!! Input video file not found for Asset ID {asset.id} at path: {source_video_path}")
            asset.processing_status = 'failed'
            asset.save(update_fields=['processing_status'])
            raise FileNotFoundError(f"Input file not found for asset {asset.id} at {source_video_path}")

        asset.processing_status = 'processing'
        asset.save(update_fields=['processing_status'])

        source_video_path_str = str(source_video_path)
        temp_dir = Path(settings.MEDIA_ROOT) / 'temp_processed'
        temp_dir.mkdir(exist_ok=True)
        processed_video_path = temp_dir / f"{asset.id}.mp4"

        ffmpeg_command = ['ffmpeg', '-i', source_video_path_str, '-c:v', 'libx264', '-b:v',
                          settings.FFMPEG_VIDEO_BITRATE, '-preset', 'fast', '-y', str(processed_video_path)]

        try:
            logger.info(f"Executing FFmpeg command: {' '.join(ffmpeg_command)}")
            result = subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True, encoding='utf-8')
            logger.info(f"FFmpeg STDOUT:\n{result.stdout}")
        except subprocess.CalledProcessError as e:
            logger.error("!!! FFmpeg command failed !!!")
            logger.error(f"--- FFmpeg STDERR ---\n{e.stderr}")
            raise

        video_url = storage_service.save_processed_video(
            local_temp_path=str(processed_video_path),
            asset=asset
        )
        # [关键修复] 移除此行，因为 storage_service.save_processed_video 已经 move 了文件
        # os.remove(processed_video_path)

        srt_url = None
        if asset.source_subtitle and hasattr(asset.source_subtitle, 'path'):
            if Path(asset.source_subtitle.path).is_file():
                srt_url = storage_service.save_source_subtitle(
                    local_srt_path=Path(asset.source_subtitle.path),
                    asset=asset
                )

        if original_status in ['completed', 'updated']:
            asset.processing_status = 'updated'
        else:
            asset.processing_status = 'completed'

        asset.processed_video_url = video_url
        asset.source_subtitle_url = srt_url
        asset.save(update_fields=['processed_video_url', 'source_subtitle_url', 'processing_status'])

        # [关键修复] 检查并更新父级 Media 的状态
        _check_and_update_media_processing_status(asset)

        logger.info(f"Successfully processed single asset: {asset.id}")
        return f"Successfully processed single asset: {asset.id}"

    except Exception as e:
        logger.error(f"为 Asset ID: {asset.id} 处理文件时发生决定性错误: {e}", exc_info=True)
        asset.processing_status = 'failed'
        asset.save(update_fields=['processing_status'])

        # [关键修复] 失败时也要更新父级 Media 的状态
        _check_and_update_media_processing_status(asset)
        raise e


@shared_task
def export_data_from_ls(media_id):
    from .models import Media

    media = None
    try:
        media = Media.objects.get(id=media_id)
        if not media.label_studio_project_id:
            logger.error(f"Media {media.id} 缺少 LS Project ID，无法导出。")
            return f"Export failed: Media {media.id} is missing LS project ID."

        project_id = media.label_studio_project_id
        logger.info(f"开始从 LS 导出 Project {project_id} 的全部数据...")

        label_studio_url = settings.LABEL_STUDIO_URL
        api_token = settings.LABEL_STUDIO_ACCESS_TOKEN
        headers = {"Authorization": f"Token {api_token}"}

        export_url = f"{label_studio_url}/api/projects/{project_id}/export"

        response = requests.get(export_url, headers=headers, stream=True)
        response.raise_for_status()

        file_name = f"ls_export_project_{project_id}.json"
        file_content = response.content

        media.label_studio_export_file.save(file_name, ContentFile(file_content), save=True)

        logger.info(f"成功导出并保存了 Project {project_id} 的标注数据到 {media.label_studio_export_file.name}")
        return f"Export successful for Media {media.id}"

    except Media.DoesNotExist:
        logger.error(f"在导出任务中找不到 ID 为 {media_id} 的 Media。")
        return f"Export failed: Media with id {media_id} not found."
    except requests.exceptions.RequestException as e:
        logger.error(f"从 LS 导出数据时 API 请求失败: {e}", exc_info=True)
        if media:
            media.l2_l3_status = 'pending'
            media.save()
        raise
    except Exception as e:
        logger.error(f"导出 LS 数据时发生未知错误: {e}", exc_info=True)
        if media:
            media.l2_l3_status = 'pending'
            media.save()
        raise


@shared_task
def generate_narrative_blueprint(media_id):
    """
    (V2 - 重构版)
    调用新版 ScriptModeler，并为其动态构建一个基于真实数据库数据的
    'mapping_provider' 函数。
    """
    from .models import Media

    logger.info(f"开始为 Media ID: {media_id} 生成叙事蓝图...")
    media = Media.objects.get(id=media_id)
    media.blueprint_status = 'processing'
    media.save(update_fields=['blueprint_status'])

    try:
        if not media.label_studio_export_file or not hasattr(media.label_studio_export_file, 'path'):
            logger.warning(f"Media {media.id} 缺少 L2/L3 标注文件，无法生成蓝图。")
            media.blueprint_status = 'failed'
            media.save(update_fields=['blueprint_status'])
            return

        # --- [关键修复] 1. 构建 Task ID 到 Asset 信息的映射表 ---
        task_id_to_asset_map = {}
        for asset in media.assets.all():
            if asset.label_studio_task_id and asset.l1_output_file and hasattr(asset.l1_output_file, 'path'):
                task_id_to_asset_map[asset.label_studio_task_id] = {
                    "chapter_id": asset.sequence_number,
                    "ass_path": asset.l1_output_file.path
                }

        # --- [关键修复] 2. 定义符合新版 ScriptModeler 接口的 mapping_provider 函数 ---
        def get_mapping_from_db(task_id: int):
            """一个闭包，用于从我们预先构建的映射表中查找数据。"""
            return task_id_to_asset_map.get(task_id)

        # --- [关键修复] 3. 实例化新版 ScriptModeler ---
        modeler = ScriptModeler(
            ls_json_path=Path(media.label_studio_export_file.path),
            project_name=media.title,  # 使用 Media 的标题作为项目名
            language=media.language,
            mapping_provider=get_mapping_from_db
        )
        final_structured_script = modeler.build()

        # ... (保存最终产物的逻辑保持不变) ...
        blueprint_content = json.dumps(final_structured_script, indent=2, ensure_ascii=False)
        blueprint_filename = f"structured_script_{media.id}.json"
        media.final_blueprint_file.save(blueprint_filename, ContentFile(blueprint_content.encode('utf-8')), save=False)

        media.blueprint_status = 'completed'
        media.save(update_fields=['final_blueprint_file', 'blueprint_status'])

        logger.info(f"成功为 Media ID: {media.id} 生成并保存了叙事蓝图！")
        return f"Blueprint generated successfully for Media {media.id}"

    except Exception as e:
        logger.error(f"为 Media ID: {media.id} 生成叙事蓝图时发生错误: {e}", exc_info=True)
        media.blueprint_status = 'failed'
        media.save(update_fields=['blueprint_status'])
        raise


@shared_task
def ingest_media_files(media_id):
    from .models import Media, Asset

    media = None
    try:
        media = Media.objects.get(id=media_id)
        # [关键修复] 更新上传状态
        media.upload_status = 'uploading'
        media.processing_status = 'processing'  # 开始处理，立即更新
        media.save(update_fields=['upload_status', 'processing_status'])

        upload_dir = Path(settings.MEDIA_ROOT) / 'batch_uploads' / str(media.id)
        if not upload_dir.exists():
            media.ingestion_status = 'failed'
            media.save()
            logger.warning(f"未找到 Media ID: {media.id} 的上传目录: {upload_dir}")
            return f"Ingestion failed: Upload directory not found for Media {media.id}"

        video_files = list(upload_dir.glob('*.mp4')) + list(upload_dir.glob('*.mov'))
        logger.info(f"在 {upload_dir} 中找到 {len(video_files)} 个视频文件。")

        for video_path in video_files:
            base_name = video_path.stem
            srt_path = upload_dir / f"{base_name}.srt"

            # [关键修复] 使用列表推导式，代码更清晰，且能被类型检查器正确解析
            digits = "".join([char for char in base_name if char.isdigit()])
            sequence_number = int(digits) if digits else 0

            asset, created = Asset.objects.get_or_create(
                media=media,
                sequence_number=sequence_number,
                defaults={'title': base_name}
            )
            logger.info(f"已创建/找到 Asset: {asset.title}")

            # [关键修复] 在触发下游任务前，将物理文件关联到数据库记录中
            with video_path.open('rb') as f:
                asset.source_video.save(video_path.name, File(f), save=False)
            if srt_path.exists():
                with srt_path.open('rb') as f:
                    asset.source_subtitle.save(srt_path.name, File(f), save=False)
            asset.save()

            process_single_asset_files.delay(str(asset.id))

        # [关键修复] 更新上传状态为完成
        media.upload_status = 'completed'
        media.save(update_fields=['upload_status'])
        logger.info(f"Media ID: {media.id} 的所有文件已加载处理完毕。")
        return f"Ingestion complete for Media {media.id}"

    except Exception as e:
        logger.error(f"为 Media ID: {media.id} 批量加载文件时发生错误: {e}", exc_info=True)
        if media:
            media.ingestion_status = 'failed'
            media.save()
        raise


@shared_task
def generate_character_report(media_id):
    """
    (V1.1) 为一个Media下的所有L1产出物(.ass)生成角色名审计报告。
    报告中的来源信息已优化为人类可读的 "序号 - 标题" 格式。
    """
    from .models import Media

    logger.info(f"开始为 Media ID: {media_id} 生成角色名审计报告...")
    media = Media.objects.get(id=media_id)

    try:
        # --- 1. 数据提取与聚合 ---
        # [关键修复] 'files' -> 'sources'，用于存储更友好的来源信息
        dialogue_counts = defaultdict(lambda: {'count': 0, 'sources': set()})
        total_dialogue_lines = 0
        total_caption_lines = 0
        total_effective_chars = 0

        assets = media.assets.all().order_by('sequence_number')
        if not assets:
            logger.warning(f"Media {media.id} 下没有任何 Asset，无法生成报告。")
            return "No assets found."

        for asset in assets:
            if not asset.l1_output_file or not hasattr(asset.l1_output_file, 'path'):
                continue

            ass_path = Path(asset.l1_output_file.path)
            if not ass_path.is_file():
                continue

            # [关键修复] 构建人类可读的来源标识
            user_friendly_source = f"{asset.sequence_number} - {asset.title}"

            in_events = False
            with ass_path.open('r', encoding='utf-8-sig') as f:
                for line in f:
                    line_strip = line.strip()
                    if line_strip.lower() == "[events]":
                        in_events = True
                        continue
                    if not in_events or not line_strip.lower().startswith("dialogue:"):
                        continue

                    try:
                        parts = line_strip.split(',', 9)
                        if len(parts) < 10: continue

                        name = parts[4].strip()
                        text = parts[9]

                        total_dialogue_lines += 1

                        if name.upper() == 'CAPTION':
                            total_caption_lines += 1
                        else:
                            dialogue_counts[name]['count'] += 1
                            # [关键修复] 记录友好的来源信息，而不是文件名
                            dialogue_counts[name]['sources'].add(user_friendly_source)
                            clean_text = re.sub(r'\{.*?\}', '', text)
                            total_effective_chars += len(clean_text)

                    except IndexError:
                        continue

        # --- 2. 构建CSV报告 ---
        output = StringIO()
        writer = csv.writer(output)

        writer.writerow(['--- Macro Audit Summary ---'])
        writer.writerow(['Metric', 'Value'])
        writer.writerow(['Language', media.language])
        writer.writerow(['Total ASS Files Audited', assets.count()])
        writer.writerow(['Total Dialogue Lines', total_dialogue_lines])
        writer.writerow(['Total Unique Character Names', len(dialogue_counts)])
        writer.writerow(['Total Caption Lines', total_caption_lines])
        writer.writerow(['Total Effective Characters', total_effective_chars])
        writer.writerow([])

        writer.writerow(['--- Detailed Character List ---'])
        # [关键修复] 更新CSV表头
        header = ["character_name", "dialogue_count", "percentage", "source_assets"]
        writer.writerow(header)

        total_character_dialogues = sum(d['count'] for d in dialogue_counts.values())
        sorted_characters = sorted(dialogue_counts.items(), key=lambda item: item[1]['count'], reverse=True)

        for name, data in sorted_characters:
            count = data['count']
            percentage = f"{(count / total_character_dialogues) * 100:.2f}%" if total_character_dialogues > 0 else "0.00%"
            # [关键修复] 从 'sources' 集合中生成字符串
            sources_str = ", ".join(sorted(list(data['sources'])))
            writer.writerow([name, count, percentage, sources_str])

        # --- 3. 保存到模型 ---
        csv_content = output.getvalue()
        report_filename = f"character_audit_{media.id}.csv"
        media.character_audit_report.save(report_filename, ContentFile(csv_content.encode('utf-8-sig')), save=True)

        logger.info(f"成功为 Media ID: {media.id} 生成并保存了角色名审计报告。")
        return f"Character audit report generated successfully for Media {media.id}"

    except Exception as e:
        logger.error(f"为 Media ID: {media.id} 生成角色名审计报告时发生错误: {e}", exc_info=True)
        raise


@shared_task
def validate_blueprint(media_id):
    """
    (V2 - 语境感知版) 为一个Media的最终产出物(structured_script.json)执行自动化验证。
    此版本会根据Media的语言属性，选择正确的词汇表进行校验。
    """
    from .models import Media
    logger.info(f"开始为 Media ID: {media_id} 验证叙事蓝图...")
    media = Media.objects.get(id=media_id)

    if not media.final_blueprint_file or not hasattr(media.final_blueprint_file, 'path'):
        logger.warning(f"Media {media.id} 缺少最终叙事蓝图文件，无法验证。")
        return "Validation failed: Blueprint file not found."

    try:
        with open(media.final_blueprint_file.path, 'r', encoding='utf-8') as f:
            blueprint = json.load(f)
    except Exception as e:
        logger.error(f"无法读取或解析 Media {media.id} 的蓝图文件: {e}")
        return "Validation failed: Cannot parse blueprint file."

    errors = []

    # [关键修复] 使用硬编码的、支持多语言的嵌套结构
    VOCABULARIES = {
        'mood_and_atmosphere': {
            'zh-CN': {"浪漫", "温馨", "喜悦", "平静", "紧张", "悬疑", "悲伤", "愤怒", "冲突", "恐惧", "压抑", "诡异"},
            'en-US': {"Romantic", "Warm", "Joyful", "Calm", "Tense", "Suspenseful", "Sad", "Angry", "Confrontational",
                      "Fearful", "Oppressive", "Eerie"}
        },
        'type': {
            'zh-CN': {"动作片段", "情感片段", "对话片段", "悬念片段", "信息片段", "幽默片段"},
            'en-US': {"Action Clip", "Emotional Clip", "Dialogue Clip", "Suspense Clip", "Revelation Clip",
                      "Humorous Clip"}
        },
        'mood': {
            'zh-CN': {"燃", "爽", "虐", "甜", "爆笑", "恐怖", "治愈", "感动", "紧张"},
            'en-US': {"Exciting", "Satisfying", "Heart-wrenching", "Sweet", "Hilarious", "Terrifying", "Healing",
                      "Touching", "Tense"}
        },
        'scene_content_type': {
            'zh-CN': {"对话驱动", "动作驱动", "内心独白", "视觉叙事"},
            'en-US': {"Dialogue_Heavy", "Action_Driven", "Internal_Monologue", "Visual_Storytelling"}
        }
    }

    # [关键修复] 获取当前Media的语言语境
    media_language = media.language

    # --- 规则1: 数据结构完整性检查 ---
    scenes = blueprint.get('scenes', {})
    for scene_id, scene in scenes.items():
        for key in ['id', 'name', 'chapter_id', 'inferred_location', 'character_dynamics', 'mood_and_atmosphere',
                    'scene_content_type', 'branch']:
            if key not in scene:
                errors.append({"scene_id": scene_id, "rule_violated": "规则1b: Scene必填项缺失",
                               "error_details": f"场景对象缺少必需的键 '{key}'。"})

        for dialogue in scene.get('dialogues', []):
            for key in ['speaker', 'content', 'start_time', 'end_time']:
                if key not in dialogue:
                    errors.append({"scene_id": scene_id, "rule_violated": "规则1c: Dialogue必填项缺失",
                                   "error_details": f"对话对象缺少必需的键 '{key}'。"})

    # --- 规则2: 受控词表校验 ---
    for scene_id, scene in scenes.items():
        # [关键修复] 动态选择正确的词汇表进行验证
        valid_moods = VOCABULARIES['mood_and_atmosphere'].get(media_language, set())
        if scene.get('mood_and_atmosphere') not in valid_moods:
            errors.append({"scene_id": scene_id, "rule_violated": "规则2a: 场景情绪无效",
                           "error_details": f"值 '{scene.get('mood_and_atmosphere')}' 不在语言 '{media_language}' 的预定义词汇表中。"})

        valid_content_types = VOCABULARIES['scene_content_type'].get(media_language, set())
        if scene.get('scene_content_type') not in valid_content_types:
            errors.append({"scene_id": scene_id, "rule_violated": "规则2d: 场景内容类型无效",
                           "error_details": f"值 '{scene.get('scene_content_type')}' 不在语言 '{media_language}' 的预定义词汇表中。"})

        for highlight in scene.get('highlights', []):
            valid_highlight_types = VOCABULARIES['type'].get(media_language, set())
            if highlight.get('type') not in valid_highlight_types:
                errors.append({"scene_id": scene_id, "rule_violated": "规则2c: 高光类型无效",
                               "error_details": f"值 '{highlight.get('type')}' 不在语言 '{media_language}' 的预定义词汇表中。"})

            valid_highlight_moods = VOCABULARIES['mood'].get(media_language, set())
            if highlight.get('mood') not in valid_highlight_moods:
                errors.append({"scene_id": scene_id, "rule_violated": "规则2c: 高光情绪无效",
                               "error_details": f"值 '{highlight.get('mood')}' 不在语言 '{media_language}' 的预定义词汇表中。"})

    # --- 规则3: 时间线逻辑一致性检查 ---
    timeline = blueprint.get('narrative_timeline', {})
    if timeline.get('type') == 'linear':
        start_count = sum(1 for scene in scenes.values() if scene.get('timeline_marker', {}).get('type') == 'START')
        if start_count == 0:
            errors.append({"scene_id": "N/A", "rule_violated": "规则3a: START标记缺失",
                           "error_details": "线性叙事中没有找到任何 START 标记。"})
        if start_count > 1:
            errors.append({"scene_id": "N/A", "rule_violated": "规则3a: START标记重复",
                           "error_details": f"线性叙事中找到了 {start_count} 个 START 标记，应仅有一个。"})

    # --- 保存报告 ---
    report = {"validation_time": datetime.now(timezone.utc).isoformat(), "errors": errors}
    media.blueprint_validation_report = report
    media.save(update_fields=['blueprint_validation_report'])

    logger.info(f"成功为 Media ID: {media.id} 生成了蓝图验证报告，发现 {len(errors)} 个错误。")
    return f"Blueprint validation report generated for Media {media.id}"