import json
import logging
import os
import subprocess
import threading
from pathlib import Path
from queue import Empty, Queue

import cv2
import numpy as np
import pandas as pd
import torch

from apps.atomflow.dubbing import constants, utils

logger = logging.getLogger(__name__)


class InpaintingService:
    """
    [物理算子] 视频去字幕服务
    """

    @staticmethod
    def run(video_path: Path, ocr_csv_path: Path, output_path: Path) -> str:
        logger.info(f"Inpainting: Processing {video_path.name}...")

        engine = InpaintingEngineHelper(model_path=constants.LAMA_MODEL_PATH)
        engine.run(str(video_path), str(ocr_csv_path), str(output_path))

        del engine
        utils.cleanup_gpu()
        return str(output_path)


class SafeVideoReader(utils.FFmpegVideoReader):
    """CPU-based FFmpeg reader to avoid CUDA context contention"""

    def _start_ffmpeg(self):
        cmd = [
            "ffmpeg",
            "-loglevel",
            "error",  # [Fix] 降低日志级别，防止 stderr 缓冲区填满导致死锁
            "-i",
            self.path,
            "-f",
            "image2pipe",
            "-pix_fmt",
            "bgr24",
            "-vcodec",
            "rawvideo",
            "-",
        ]
        # stderr=None 继承父进程 stderr。高频日志输出会导致管道阻塞，生产环境建议静音。
        return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=None, bufsize=10**7)


class InpaintingEngineHelper:
    def __init__(self, model_path, device="cuda"):
        self.device = device
        logger.info(f"[Inpainting] Loading TorchScript model from {model_path} on {device}...")

        # [Architecture Change] Switch from ONNX to PyTorch (TorchScript)
        # Reason: LaMa uses FFT operators which often cause CPU fallback in ONNX Runtime,
        # resulting in severe performance degradation (140s/frame). PyTorch handles FFT natively on CUDA.
        self.model = torch.jit.load(model_path, map_location=device)
        self.model.eval()
        self.model.to(device)

        # 缓存上一帧的重绘区域，用于减少时序闪烁 (Temporal Flicker)
        self.prev_inpainted_area = None
        self.prev_roi = None  # (x1, y1, x2, y2)

        # Warmup
        if device == "cuda":
            try:
                dummy_img = torch.zeros((1, 3, 512, 512), device=device)
                dummy_mask = torch.zeros((1, 1, 512, 512), device=device)
                with torch.no_grad():
                    self.model(dummy_img, dummy_mask)
                logger.info("[Inpainting] Warmup completed.")
            except Exception:
                pass

    def _get_expanded_mask(self, mask):
        """
        [Optimization] 激进掩码策略 (来自新方案)
        短剧字幕常有投影/发光，简单的膨胀不够，使用多级膨胀+羽化
        """
        # [Fix] 增强掩码扩张强度以解决文字残留问题。
        # 原有 (30, 10) 内核对于带描边或阴影的字幕可能不够大。
        # 增加内核尺寸和模糊半径，确保完全覆盖字幕区域并平滑过渡。

        # 第一级：更大范围地膨胀以捕捉阴影/描边
        kernel_large = cv2.getStructuringElement(cv2.MORPH_RECT, (51, 21))
        mask_dilated = cv2.dilate(mask, kernel_large, iterations=1)

        # 第二级：高斯模糊实现边缘羽化，让 AI 融合更自然
        # 结果归一化到 0.0 - 1.0 用于 Alpha Blending
        mask_floated = cv2.GaussianBlur(mask_dilated.astype(np.float32), (21, 21), 0) / 255.0
        return mask_floated

    def _interpolate_ocr_map(self, ocr_map, max_gap=8):
        """
        [Optimization] 填补 OCR 采样造成的空隙 (Temporal Interpolation)
        由于 OCR 采用 sample_step=5 采样，会导致中间帧无数据，Inpainting 会出现闪烁。
        此处简单地将上一帧的检测结果延续到下一帧之前。
        """
        if not ocr_map:
            return ocr_map

        sorted_fids = sorted(ocr_map.keys())
        new_map = ocr_map.copy()

        for i in range(len(sorted_fids) - 1):
            curr_f = sorted_fids[i]
            next_f = sorted_fids[i + 1]

            # 如果两个关键帧之间间隔很小（说明是采样间隙），则进行填充
            # max_gap 设为 8 以覆盖 sample_step=5 的情况
            if next_f - curr_f <= max_gap:
                # 使用当前帧的框填充中间帧
                boxes = ocr_map[curr_f]
                for gap_f in range(curr_f + 1, next_f):
                    new_map[gap_f] = boxes

        return new_map

    def run(self, video_path, ocr_csv_path, output_path):
        if not os.path.exists(ocr_csv_path):
            logger.warning("OCR index not found. Skipping inpainting.")
            return

        df = pd.read_csv(ocr_csv_path)
        ocr_map = {}
        for _, row in df.iterrows():
            try:
                boxes = json.loads(row["boxes"])
                if boxes:
                    ocr_map[int(row["frame_idx"])] = boxes
            except:  # noqa: E722
                continue

        # [Optimization] 时序插值，填补采样空隙
        ocr_map = self._interpolate_ocr_map(ocr_map)

        logger.info(
            f"   [Inpainting] Loaded OCR map with {len(ocr_map)} frames containing subtitles (after interpolation)."
        )

        cap = SafeVideoReader(video_path)
        # [Fix] 必须获取 total_frames 用于进度计算，如果获取失败则设为未知
        total_frames = cap.total_frames if cap.total_frames > 0 else 0
        width, height, fps, total_frames = cap.width, cap.height, cap.fps, cap.total_frames

        writer_cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",  # [Fix] 降低日志级别，防止 stderr 缓冲区填满导致死锁
            "-f",
            "rawvideo",
            "-vcodec",
            "rawvideo",
            "-s",
            f"{width}x{height}",
            "-pix_fmt",
            "bgr24",
            "-r",
            f"{fps}",
            "-i",
            "-",
            "-c:v",
            "h264_nvenc",
            "-preset",
            "p4",
            "-cq",
            "21",  # [Optimization] Switch back to GPU encoding (PyTorch is stable)
            "-pix_fmt",
            "yuv420p",
            output_path,
        ]
        # 增大管道缓冲区 (bufsize=10MB)
        writer = subprocess.Popen(writer_cmd, stdin=subprocess.PIPE, stderr=None, bufsize=10**7)

        # --- 异步队列设计 ---
        # 限制队列大小以防止内存溢出 (OOM)，同时提供足够的缓冲
        # [Fix] 减小队列大小 (64->16)，降低内存压力，避免 GC 卡顿
        read_queue = Queue(maxsize=16)
        write_queue = Queue(maxsize=16)
        error_event = threading.Event()

        def reader_worker():
            """线程1: 负责从 FFmpeg 读取原始帧"""
            try:
                f_idx = 0
                while not error_event.is_set():
                    ret, frame = cap.read()
                    if not ret:
                        break
                    # 确保内存可写
                    if not frame.flags.writeable:
                        frame = frame.copy()

                    read_queue.put((f_idx, frame))
                    f_idx += 1
            except Exception as e:
                logger.error(f"Reader thread error: {e}")
                error_event.set()
            finally:
                # 发送结束信号
                try:
                    read_queue.put(None)
                except:  # noqa: E722
                    pass

        def processor_worker():
            """线程2: 负责 AI 推理 (LaMa) 和 图像处理"""
            # [Config] 禁用 OpenCV 多线程，防止与 PyTorch/Celery 发生线程资源竞争
            cv2.setNumThreads(0)

            try:
                while not error_event.is_set():
                    item = read_queue.get()

                    if item is None:
                        # 传递结束信号
                        try:
                            write_queue.put(None)
                        except:  # noqa: E722
                            pass
                        break

                    f_idx, frame = item

                    # --- 核心处理逻辑 ---
                    if f_idx in ocr_map:
                        boxes = ocr_map[f_idx]
                        full_mask = np.zeros((height, width), dtype=np.uint8)
                        for box in boxes:
                            box = np.array(box, dtype=np.int32)
                            cv2.fillPoly(full_mask, [box], 255)

                        points = cv2.findNonZero(full_mask)
                        if points is not None:
                            x, y, w, h_rect = cv2.boundingRect(points)
                            pad_x, pad_y = 64, 64
                            x1, y1 = max(0, x - pad_x), max(0, y - pad_y)
                            x2, y2 = min(width, x + w + pad_x), min(height, y + h_rect + pad_y)

                            crop_frame = frame[y1:y2, x1:x2].copy()
                            crop_mask = full_mask[y1:y2, x1:x2]
                            refined_mask = self._get_expanded_mask(crop_mask)

                            inpainted_crop = self._inpaint_frame(
                                cv2.cvtColor(crop_frame, cv2.COLOR_BGR2RGB), (refined_mask * 255).astype(np.uint8)
                            )
                            inpainted_crop = cv2.cvtColor(inpainted_crop, cv2.COLOR_RGB2BGR)

                            if self.prev_inpainted_area is not None and self.prev_roi == (x1, y1, x2, y2):
                                inpainted_crop = cv2.addWeighted(inpainted_crop, 0.7, self.prev_inpainted_area, 0.3, 0)

                            self.prev_inpainted_area = inpainted_crop
                            self.prev_roi = (x1, y1, x2, y2)

                            alpha = refined_mask[..., None]
                            blended_crop = (alpha * inpainted_crop + (1 - alpha) * crop_frame).astype(np.uint8)
                            frame[y1:y2, x1:x2] = blended_crop
                        else:
                            self.prev_inpainted_area = None
                            self.prev_roi = None
                    else:
                        self.prev_inpainted_area = None
                        self.prev_roi = None

                    # 将处理好的帧字节流放入写入队列
                    write_queue.put(frame.tobytes())

                    # 日志
                    if f_idx == 1 or f_idx % 50 == 0:
                        logger.info(f"   [Inpainting] Progress: {f_idx}/{total_frames} frames processed")
            except Exception as e:
                logger.error(f"Processor thread error: {e}")
                error_event.set()
                try:
                    write_queue.put(None)
                except:  # noqa: E722
                    pass

        def writer_worker():
            """线程3: 负责将结果写入 FFmpeg 编码"""
            try:
                while not error_event.is_set():
                    try:
                        data = write_queue.get(timeout=5)  # 稍微长一点的超时，允许推理波动
                    except Empty:
                        continue

                    if data is None:
                        break

                    writer.stdin.write(data)
            except Exception as e:
                logger.error(f"Writer thread error: {e}")
                error_event.set()

        logger.info("   [Inpainting] Starting Async Pipeline (Reader -> Processor -> Writer)...")

        t_read = threading.Thread(target=reader_worker, daemon=True)
        t_proc = threading.Thread(target=processor_worker, daemon=True)
        t_write = threading.Thread(target=writer_worker, daemon=True)

        t_read.start()
        t_proc.start()
        t_write.start()

        t_read.join()
        t_proc.join()
        t_write.join()

        # Cleanup
        if writer.stdin:
            writer.stdin.close()
        writer.wait()
        cap.release()

        if error_event.is_set():
            raise RuntimeError("Inpainting pipeline failed. Check logs for details.")

    def _inpaint_frame(self, img, mask):
        # [Config] 将输入 Resize 到 512x512 进行推理。
        # 虽然 LaMa 支持动态尺寸，但固定尺寸能保证推理速度稳定，且避免某些边缘情况下的维度错误。
        h_orig, w_orig = img.shape[:2]
        target_size = (512, 512)

        img_resized = cv2.resize(img, target_size, interpolation=cv2.INTER_LINEAR)
        mask_resized = cv2.resize(mask, target_size, interpolation=cv2.INTER_NEAREST)

        # Prepare Tensors
        img_t = torch.from_numpy(img_resized).float() / 255.0
        img_t = img_t.permute(2, 0, 1).unsqueeze(0).to(self.device)  # HWC -> NCHW

        mask_t = torch.from_numpy(mask_resized).float() / 255.0
        mask_t = (mask_t > 0.5).float()
        mask_t = mask_t.unsqueeze(0).unsqueeze(0).to(self.device)  # HW -> NCHW

        # Inference
        with torch.no_grad():
            output = self.model(img_t, mask_t)

        # Post-process
        output_tensor = output[0].permute(1, 2, 0).cpu().numpy()  # NCHW -> HWC
        output_img = np.clip(output_tensor * 255, 0, 255).astype(np.uint8)

        # Resize back to original dimensions
        result = cv2.resize(output_img, (w_orig, h_orig), interpolation=cv2.INTER_LINEAR)
        return result
