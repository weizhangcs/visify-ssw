#!/bin/bash

# ==============================================================================
# VSS Edge 离线依赖下载器 (PyTorch)
# 用途: 预下载 PyTorch 的 CPU 和 GPU 版本 Wheel 包到 local_packages 目录。
#       支持跨平台下载 (即在 Mac/Win 上下载 Linux Docker 所需的包)。
# ==============================================================================

# 1. 配置版本 (需与 Python 3.12 兼容)
# 目前 PyTorch 2.5.1 是支持 Python 3.12 的稳定版本
TORCH_VERSION="2.5.1"
VISION_VERSION="0.20.1"
AUDIO_VERSION="2.5.1"

# 2. 配置目标架构 (Docker 容器环境)
PYTHON_VERSION="3.12"
PLATFORM="linux_x86_64"

# 3. 路径配置
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$SCRIPT_DIR/../.."
OUTPUT_ROOT="$PROJECT_ROOT/local_packages"

echo "========================================================"
echo "   VSS Edge PyTorch Downloader"
echo "   Target: Python $PYTHON_VERSION | Platform: $PLATFORM"
echo "   Torch: $TORCH_VERSION | Vision: $VISION_VERSION | Audio: $AUDIO_VERSION"
echo "========================================================"

# -----------------------------------------------------------
# 任务 A: 下载 CPU 版本 (轻量级)
# -----------------------------------------------------------
CPU_DIR="$OUTPUT_ROOT/cpu"
echo -e "\n🚀 [1/2] Downloading CPU packages to $CPU_DIR ..."
mkdir -p "$CPU_DIR"

# 清理旧包 (可选，防止版本混杂)
rm -f "$CPU_DIR"/*.whl

pip download \
    torch==$TORCH_VERSION torchvision==$VISION_VERSION torchaudio==$AUDIO_VERSION \
    --dest "$CPU_DIR" \
    --index-url https://download.pytorch.org/whl/cpu \
    --python-version $PYTHON_VERSION \
    --platform $PLATFORM \
    --only-binary=:all: \
    --no-deps \
    --progress-bar on

# -----------------------------------------------------------
# 任务 B: 下载 GPU 版本 (CUDA 12.1)
# -----------------------------------------------------------
GPU_DIR="$OUTPUT_ROOT/gpu"
echo -e "\n🚀 [2/2] Downloading GPU (CUDA 12.1) packages to $GPU_DIR ..."
mkdir -p "$GPU_DIR"

rm -f "$GPU_DIR"/*.whl

pip download \
    torch==$TORCH_VERSION torchvision==$VISION_VERSION torchaudio==$AUDIO_VERSION \
    --dest "$GPU_DIR" \
    --index-url https://download.pytorch.org/whl/cu121 \
    --python-version $PYTHON_VERSION \
    --platform $PLATFORM \
    --only-binary=:all: \
    --no-deps \
    --progress-bar on

echo -e "\n✅ All Done! Packages are ready in $OUTPUT_ROOT"