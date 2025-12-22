import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from django.conf import settings

from apps.media_assets.models import Media

# from tqdm import tqdm # 避免在后台任务中使用 tqdm

logger = logging.getLogger(__name__)


class SynthesisService:
    """
    (V3.4 - 适配 Django)
    核心功能：加载剪辑脚本和素材，调用本地 FFmpeg 完成音轨拼接、B-roll裁切和最终合成。
    """

    def __init__(self, project_id: str):
        # 使用 MEDIA_ROOT 作为工作区基础，并在其中创建项目专属目录
        self.base_work_dir = Path(settings.MEDIA_ROOT) / "creative_synthesis"
        self.base_work_dir.mkdir(exist_ok=True)
        self.work_dir = self.base_work_dir / str(project_id)
        self.work_dir.mkdir(exist_ok=True)
        self.project_id = project_id

        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=True, encoding="utf-8")
            logger.info("ffmpeg found on system path and is functioning.")
        except Exception:
            logger.error("FATAL: ffmpeg not found or not functional.", exc_info=True)
            raise
        logger.info("SynthesisService initialized.")

    def execute(
        self,
        editing_script_path: Path,
        blueprint_path: Path,
        local_audio_base_dir: Path,
        source_videos_dir: Path,
        asset_id: str,
        **kwargs,
    ) -> Path:
        """
        执行最终合成流程。

        :param editing_script_path: editing_script.json 的绝对路径。
        :param blueprint_path: final_blueprint_file.json 的绝对路径。
        :param local_audio_base_dir: 存放所有配音音频文件的基础目录（e.g., media_root/creative/{id}/outputs/audio_{job_id}/）。
        :param source_videos_dir: 存放原始视频文件的基础目录（e.g., media_root/source_files/{asset_id}/media/）。
        :return: 最终输出视频文件的绝对路径。
        """
        logger.info("开始最终视频合成...")
        try:
            logger.info("正在加载剪辑脚本和Blueprint...")
            with editing_script_path.open("r", encoding="utf-8") as f:
                editing_script_json = json.load(f)
            with blueprint_path.open("r", encoding="utf-8") as f:
                blueprint_data = json.load(f)

            editing_script_data = editing_script_json.get("editing_script", [])
            if not editing_script_data:
                raise ValueError("Editing script is empty.")

            temp_dir = self.work_dir / "temp"
            temp_dir.mkdir(exist_ok=True)

            # --- 核心流程 ---
            final_audio_path = self._create_narration_track(editing_script_data, temp_dir, local_audio_base_dir)
            final_video_path = self._create_video_track(
                editing_script_data, blueprint_data, source_videos_dir, temp_dir, asset_id
            )

            if not final_audio_path or not final_video_path:
                raise RuntimeError("Audio or video track generation failed.")

            output_path = self._combine_audio_video(final_video_path, final_audio_path)

            logger.info("视频合成完成。")
            return output_path

        except Exception as e:
            logger.critical(f"视频合成时失败: {e}", exc_info=True)
            raise

    def _run_ffmpeg_command(self, cmd: List[str], log_label: str):
        """执行 FFmpeg 命令的封装"""
        logger.debug(f"Executing ffmpeg command for '{log_label}': {' '.join(cmd)}")
        try:
            # 捕获输出，确保 Check=True 会打印 stderr
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding="utf-8")
            if result.stderr:
                logger.debug(f"ffmpeg stderr for '{log_label}' (Ignored warnings): \n{result.stderr}")
        except subprocess.CalledProcessError as e:
            error_message = f"FFMPEG command for '{log_label}' failed with exit code {e.returncode}.\n"
            error_message += f"Command: {' '.join(e.cmd)}\n"
            error_message += f"Stderr: {e.stderr}"
            logger.error(error_message)
            raise

    def _create_narration_track(self, editing_script: List[Dict], temp_dir: Path, local_audio_base_dir: Path) -> Path:
        """
        步骤一：将所有配音片段拼接成一个完整的音轨。
        """
        logger.info("步骤 1/3: 正在合成完整配音音轨...")

        # [修改] narration_audio_path 现在是相对于 media_root/creative/{id}/outputs/audio_{job_id}/ 的相对路径
        # 因此我们需要重新构建它的绝对路径
        audio_paths = []
        for entry in editing_script:
            audio_rel_path = entry.get("narration_audio_path")
            if audio_rel_path:
                # 假设 narration_audio_path 已经在 dubbing_script.json 中被更新为 local_audio_path (相对路径)
                # 实际上，它还是云端路径，我们需要在 CreativeProject 的 dubbing_script_file 中提取 local_audio_path
                # 但由于我们目前只有一个 editing_script.json，我们假设 narration_audio_path 是相对于 local_audio_base_dir 的相对路径
                # 检查 dubbing_script.json 的逻辑 (请看下面 Creative Task 的修复)
                audio_paths.append(local_audio_base_dir / audio_rel_path)

        if not audio_paths or not audio_paths[0].is_file():
            # 我们无法在服务层修复路径，因为 dubbing_script.json 的结构决定了路径。
            # 我们必须假设上一步已经将正确的本地路径注入到 editing_script.json 中，或者我们能在这里正确解析。
            # 基于 editing_script.json 的结构（其中 narration_audio_path 仍是云端路径），这是个问题。
            # 为了避免更复杂的设计，我们暂时信任 editing_script 中的 narration_audio_path 是一个文件**名**，并且它存在于 local_audio_base_dir 中。

            # 重新修正路径提取:
            # 检查 dubbing_script.json 的 logic (在 creative/tasks.py 中)
            # 在 creative/tasks.py/finalize_audio_task 中，dubbing_script.json 被修改并保存了 local_audio_path。
            # 但是 editing_script.json (GENERATE_EDITING_SCRIPT 产出) 只接收 dubbing_script.json **作为输入**。
            # 为了简化，我们假设 editing_script.json 中的 narration_audio_path **已经被替换为** local_audio_base_dir 的相对路径。

            # 我们必须以 `local_audio_base_dir` 作为 audio_paths 的根目录来查找。

            # 由于 editing_script 结构只有 narration_audio_path (云端路径)，
            # 我们必须将 audio_file_path 替换为本地路径的逻辑移到 **finalize_edit_script_task** 任务中。
            # 但为了让 SynthesisService 跑起来，我们先简化。

            audio_files = []
            for entry in editing_script:
                audio_filename = Path(entry.get("narration_audio_path", "")).name
                local_path = local_audio_base_dir / audio_filename
                if local_path.is_file():
                    audio_files.append(local_path)
                else:
                    logger.warning(f"跳过未找到的音频文件: {local_path}")
            audio_paths = audio_files

            if not audio_paths:
                logger.error("剪辑脚本中未找到任何有效的本地配音文件。")
                return None

        first_file = audio_paths[0]
        file_extension = first_file.suffix
        logger.info(f"检测到配音文件格式为: {file_extension}")

        output_path = self.work_dir / f"final_audio{file_extension}"
        concat_list_path = temp_dir / "audio_concat_list.txt"

        with concat_list_path.open("w", encoding="utf-8") as f:
            for path in audio_paths:
                f.write(f"file '{path.resolve()}'\n")

        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list_path),
            "-c",
            "copy",
            str(output_path),
        ]
        self._run_ffmpeg_command(cmd, "Audio Concatenation")

        logger.info(f"✅ 配音音轨合成完毕: {output_path}")
        return output_path

    def _create_video_track(
        self,
        editing_script: List[Dict],
        blueprint_data: Dict,  # ⚠️ blueprint_data 仅用于日志，不再用于核心查找
        source_videos_dir: Path,
        temp_dir: Path,
        asset_id: str,
    ) -> Path:
        """
        步骤二：裁切和拼接 B-roll 视频轨道。
        """
        logger.info("步骤 2/3: 正在裁切和拼接B-roll视频轨道...")

        # --- [START OF MODIFIED LOGIC: 建立 Media ID -> 路径 的可靠映射] ---
        # 目标: 建立 {Media ID (UUID): Path Object} 的映射，以供 B-roll 片段直接查找
        source_video_map = {}
        try:
            # 1. 查找所有 Media 文件 (Media.id 即 Chapter ID - UUID)
            media_files = Media.objects.filter(asset_id=asset_id, source_video__isnull=False)

            for media in media_files:
                if media.source_video and media.source_video.path and Path(media.source_video.path).is_file():
                    # 使用 Media ID (UUID) 作为查找键，确保与 editing_script 中的 chapter_id 匹配
                    source_video_map[str(media.id)] = Path(media.source_video.path)
                    logger.debug(f"建立映射: Media ID {media.id} -> {Path(media.source_video.path).name}")

            if not source_video_map:
                logger.error(f"Asset ID {asset_id} 下没有找到任何可用的源视频文件，请检查 Media.source_video。")

        except Exception as e:
            logger.error(f"建立源视频映射时发生错误: {e}", exc_info=True)
        # --- [END OF MODIFIED LOGIC] ---

        # 移除对 blueprint_data 的依赖：
        # chapters_dict = blueprint_data.get("chapters", {}) # 冗余
        # scenes_dict = blueprint_data.get("scenes", {}) # 冗余
        # scene_to_chapter_map = {str(scene["id"]): str(scene["chapter_id"]) for scene in scenes_dict.values()} # 冗余

        # 核心查找映射现在是 source_video_map，无需额外的 chapter_map
        # chapter_map = {} # 冗余

        clip_files = []

        for i, entry in enumerate(editing_script):
            for j, clip in enumerate(entry.get("b_roll_clips", [])):
                # --- [适配新 VSS Cloud 输出] ---
                chapter_id = clip.get("chapter_id")

                if not chapter_id:
                    logger.warning(f"剪辑片段 {i}-{j} 缺少 chapter_id，跳过。")
                    continue

                # 直接通过 chapter_id (Media ID) 查找源视频路径
                source_video = source_video_map.get(chapter_id)

                # 检查文件存在性
                if not source_video or not source_video.is_file():
                    logger.error(
                        f"无法找到 Chapter {chapter_id} 对应的有效源视频文件。请检查 Media.id 是否匹配，或文件是否存在。路径: {source_video}"
                        # noqa: E501
                    )
                    continue

                temp_clip_path = temp_dir / f"clip_{i:03d}_{j:03d}.mp4"  # noqa: E231

                # 确保 start_time 和 duration 是字符串/可用于 -ss/-t 参数
                start_time = clip.get("start_time")
                duration = clip.get("duration")

                if not start_time or not duration:
                    logger.warning(f"剪辑片段 {i}-{j} 缺少 start_time 或 duration，跳过。")
                    continue

                cmd = [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    start_time,
                    "-i",
                    str(source_video),
                    "-t",
                    str(duration),
                    "-an",
                    "-vcodec",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    str(temp_clip_path),
                ]
                self._run_ffmpeg_command(cmd, f"Slicing clip {i}-{j}")
                clip_files.append(temp_clip_path)

        output_path = self.work_dir / "final_video_no_audio.mp4"
        if not clip_files:
            logger.error("未能裁切出任何有效的视频片段。")
            return None

        concat_list_path = temp_dir / "video_concat_list.txt"
        with concat_list_path.open("w", encoding="utf-8") as f:
            for clip_path in clip_files:
                f.write(f"file '{clip_path.resolve()}'\n")

        # 拼接视频
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list_path),
            "-c",
            "copy",
            str(output_path),
        ]
        self._run_ffmpeg_command(cmd, "Video Concatenation")

        logger.info(f"✅ B-roll视频轨道拼接完毕: {output_path}")
        return output_path

    def _combine_audio_video(self, video_path: Path, audio_path: Path) -> Path:
        """
        步骤三：合并音视频，生成最终成片。
        """
        logger.info("步骤 3/3: 正在合并音视频，生成最终成片...")
        output_path = self.work_dir / f"final_output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"

        # 原始的 FFmpeg 命令
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(output_path),
        ]
        self._run_ffmpeg_command(cmd, "Final Combination")

        logger.info(f"🎉 视频合成完毕！输出路径: {output_path}")
        return output_path
