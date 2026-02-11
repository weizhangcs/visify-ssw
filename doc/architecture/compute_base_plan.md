# VSS Compute Base 工程化方案

## 1. 背景与目标
**项目名称**: `vss-compute-base`
**目标**: 构建一个独立的、全能算力底座 Docker 镜像，供主业务项目 (`vss-edge`) 引用。
**痛点解决**:
*   主项目构建时间过长。
*   FFmpeg (NVENC) 与 Python/AI 库的依赖环境难以在同一个 Dockerfile 中维护（依赖地狱）。

## 2. 技术策略
1.  **反转继承 (Inverted Inheritance)**:
    *   放弃 "将 FFmpeg 拷贝到 Python 镜像" 的方案。
    *   采用 "在完善的 FFmpeg/CUDA 镜像中安装 Python" 的方案。
    *   Base Image: `jrottenberg/ffmpeg:6.0-nvidia` (Ubuntu 22.04 + CUDA + NVENC)。
2.  **分层构建**:
    *   **Layer 1 (System)**: Python 3.12 (via PPA), OpenCV libs, Build tools.
    *   **Layer 2 (Compute)**: PyTorch (GPU), Numpy.
    *   **Layer 3 (Algorithm)**: Demucs, Librosa, OpenCV-Headless, Transformers.
3.  **验证闭环**:
    *   包含 `verify_env.py` 脚本，构建后立即验证 GPU、NVENC 和 AI 库可用性。

## 3. 项目结构规划

```text
vss-compute-base/
├── Dockerfile             # 核心构建文件
├── requirements.txt       # 核心 Python 依赖
├── scripts/
│   └── verify_env.py      # 环境验证脚本
└── README.md
```

## 4. 核心文件草稿

### 4.1 Dockerfile

```dockerfile
# syntax=docker/dockerfile:1
# Base: jrottenberg/ffmpeg:6.0-nvidia (Ubuntu 22.04 + CUDA 11.8/12.x + NVENC)
FROM jrottenberg/ffmpeg:6.0-nvidia

ARG APT_MIRROR=mirrors.aliyun.com
ARG PIP_MIRROR_URL=https://mirrors.aliyun.com/pypi/simple/

# -----------------------------------------------------------------------------
# 1. 系统基础环境 (System Layer)
# -----------------------------------------------------------------------------
USER root
ENV DEBIAN_FRONTEND=noninteractive \
    LC_ALL=C.UTF-8 \
    LANG=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 重置 Entrypoint (原镜像默认为 ffmpeg)
ENTRYPOINT []

# 换源并安装 Python 3.12 + OpenCV 系统依赖 + 常用工具
RUN sed -i "s|archive.ubuntu.com|$APT_MIRROR|g" /etc/apt/sources.list && \
    sed -i "s|security.ubuntu.com|$APT_MIRROR|g" /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        software-properties-common wget curl git build-essential \
        libsndfile1 libgomp1 \
        libgl1 libglib2.0-0 \
        fonts-wqy-zenhei \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        python3.12 python3.12-dev python3.12-distutils python3.12-venv \
    && curl -sS https://bootstrap.pypa.io/get-pip.py | python3.12 \
    && ln -sf /usr/bin/python3.12 /usr/bin/python \
    && ln -sf /usr/bin/python3.12 /usr/bin/python3 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# 配置全局 pip 源
RUN pip config set global.index-url $PIP_MIRROR_URL && \
    pip config set global.timeout 1000

# -----------------------------------------------------------------------------
# 2. 核心算力层 (Compute Layer - PyTorch)
# -----------------------------------------------------------------------------
# 在线安装 GPU 版 Torch (利用 Docker 缓存)
# 这里的版本需与 CUDA 12.x 兼容
RUN pip install --no-cache-dir \
    torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 \
    --index-url https://download.pytorch.org/whl/cu121

# -----------------------------------------------------------------------------
# 3. 媒体算法层 (Algorithm Layer)
# -----------------------------------------------------------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# -----------------------------------------------------------------------------
# 4. 验证脚本
# -----------------------------------------------------------------------------
COPY scripts/verify_env.py /usr/local/bin/verify_env.py
```

### 4.2 requirements.txt

```text
numpy==1.26.4
# OpenCV (CPU版，用于像素处理，解码交给 FFmpeg)
opencv-python-headless
# 音频处理
librosa
pydub==0.25.1
# 音频分离 (依赖 Torch)
demucs
# 向量化/NLP
sentence-transformers
```

### 4.3 scripts/verify_env.py

```python
import sys
import subprocess

def check_gpu_torch():
    try:
        import torch
        print(f"[PyTorch] Version: {torch.__version__}")
        print(f"[PyTorch] CUDA Available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"[PyTorch] Device: {torch.cuda.get_device_name(0)}")
            return True
        return False
    except ImportError:
        print("[PyTorch] Not installed")
        return False

def check_ffmpeg_nvenc():
    try:
        result = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True)
        if "h264_nvenc" in result.stdout:
            print("[FFmpeg] NVENC found: YES")
            return True
        print("[FFmpeg] NVENC found: NO")
        return False
    except Exception as e:
        print(f"[FFmpeg] Error: {e}")
        return False

def check_demucs():
    try:
        import demucs
        print(f"[Demucs] Installed: YES")
        return True
    except ImportError:
        print("[Demucs] Not installed")
        return False

if __name__ == "__main__":
    print("=== VSS Compute Base Verification ===")
    checks = [check_gpu_torch(), check_ffmpeg_nvenc(), check_demucs()]
    
    if all(checks):
        print("\n✅ Environment is READY for GPU Compute.")
        sys.exit(0)
    else:
        print("\n❌ Environment Verification FAILED.")
        sys.exit(1)
```