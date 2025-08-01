# Dockerfile

# 1. 使用官方的 Python 3.12 镜像作为基础
FROM python:3.12-slim

# 2. 设置环境变量
ENV PYTHONDONTWRITEBYTECODE 1  # 防止 python 生成 .pyc 文件
ENV PYTHONUNBUFFERED 1         # 确保 Python 输出能直接在 Docker 日志中看到

# 3. [优化] 更换软件源为国内高速镜像，并首先安装系统级依赖
#    这一层非常稳定，几乎不会变动，因此会被长期缓存
RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 4. 设置工作目录
WORKDIR /app

# 5. 复制并安装 Python 依赖
#    只有当 requirements.txt 文件变化时，这一层及之后的缓存才会失效
COPY requirements.txt .
RUN pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 6. 最后才复制项目源代码
#    这是变动最频繁的部分，放在最后，可以最大化利用前面所有层的缓存
COPY . .