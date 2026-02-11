#!/bin/bash

# ==============================================================================
# VSS Edge 离线模型下载器
# 用途: 预下载 Embedding 模型到 local_models 目录，供 Docker 构建或本地离线运行。
# ==============================================================================

# 1. 配置模型名称 (需与 apps/vector/services/embedding.py 保持一致)
MODEL_NAME="intfloat/multilingual-e5-large"

# 2. 配置输出目录 (相对于项目根目录)
OUTPUT_DIR="local_models"

# 获取当前脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# 检查 Python 环境
if command -v python &>/dev/null; then
    PYTHON_CMD=python
elif command -v python3 &>/dev/null; then
    PYTHON_CMD=python3
else
    echo "Error: Python not found. Please install Python to run the downloader."
    exit 1
fi

# 执行下载
$PYTHON_CMD "$SCRIPT_DIR/download_model.py" --model "$MODEL_NAME" --output "$OUTPUT_DIR"