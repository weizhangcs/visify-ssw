# Dockerfile

# 1. 使用官方的 Python 3.13 镜像作为基础
FROM python:3.13-slim

# 2. 设置环境变量
ENV PYTHONDONTWRITEBYTECODE 1  # 防止 python 生成 .pyc 文件
ENV PYTHONUNBUFFERED 1         # 确保 Python 输出能直接在 Docker 日志中看到

# 3. 设置工作目录
WORKDIR /app

RUN apt-get update && apt-get install -y ffmpeg

# 4. 复制依赖文件并安装依赖
#    将这一步放在复制全部代码之前，可以利用 Docker 的缓存机制，
#    只要 requirements.txt 不变，就不需要重新安装依赖，加快构建速度。
COPY requirements.txt .
RUN pip install -i https://pypi.org/simple -r requirements.txt

# 5. 复制项目代码到工作目录
COPY . .