VSS Edge/Cloud Testbench 标准化工作指南
版本: 1.0

适用环境: Windows 宿主机 (VirtualBox) + Ubuntu 24.04 Guest

核心目标: 1. 解决中国大陆网络环境下的依赖安装与 Docker 构建问题。 2. 实现 Edge/Cloud 业务的拟真网络环境（VPN 访问外网 + 局域网高速互通）。 3. 彻底解决 PyTorch 导致的镜像臃肿与推送失败问题。

🛠️ 第一阶段：宿主机与虚拟机配置
1. VirtualBox 网络设置
在启动 Ubuntu 虚拟机前，请确保网络适配器配置如下：

网卡 1 (Adapter 1): NAT

作用: 默认网关，走宿主机 VPN 访问 Google/Gemini API。

网卡 2 (Adapter 2): Bridged Adapter (桥接网卡)

作用: 局域网互通，SSH 连接，大文件传输。

2. 本地资源准备 (Windows 宿主机)
为了实现“离线加速构建”，请在项目根目录创建 local_packages/ 文件夹，并下载以下文件（利用宿主机 VPN）：

目标路径: 项目根目录/local_packages/

下载内容: 适配 Python 3.12 + Linux x86_64 的 CPU 版本 PyTorch。

torch-2.5.1+cpu-cp312-cp312-linux_x86_64.whl

torchvision-0.20.1+cpu-cp312-cp312-linux_x86_64.whl

下载源: PyTorch Official WHL

🚀 第二阶段：Guest OS 初始化 (一键脚本)
在 Ubuntu 虚拟机内运行。

步骤 1: 系统与 Docker 初始化
状态: 宿主机 VPN 关闭 (利用国内直连速度)

脚本: install_deps_fixed.sh

功能: 自动配置阿里云系统源 (Ubuntu 24.04 DEB822 格式)、配置阿里云 Docker 源、安装 Docker Engine、配置用户权限。

Bash

# 传输脚本到虚拟机后执行
sudo chmod +x install_deps_fixed.sh
sudo ./install_deps_fixed.sh --cn
步骤 2: 双网卡路由分流
状态: 宿主机 VPN 开启 (业务拟真)

脚本: 03_config_routing_fixed.sh

功能: 自动识别网卡，将 NAT 网卡优先级设为 100 (默认出口)，桥接网卡优先级设为 200 (仅内网)。

Bash

sudo chmod +x 03_config_routing_fixed.sh
sudo ./03_config_routing_fixed.sh
🐳 第三阶段：Docker 镜像构建 (核心瘦身方案)
本方案解决了“既要国内快，又要 Torch 不超时，还要镜像小”的悖论。

1. 核心策略
离线搬运 (Offline Injection): 宿主机下载 CPU 版 Torch whl，COPY 进镜像安装。

全局换源 (Global Config): Dockerfile 内全局设置 pip 阿里云源，防止依赖包下载超时。

挂载模型 (Mounting): 绝不 COPY 模型文件进镜像，部署时通过 -v 挂载。

2. 标准 Dockerfile 模板 (Media/Workbench 通用)
Dockerfile

# 基础镜像
FROM crpi-34v4qt829vtet2cy.cn-hangzhou.personal.cr.aliyuncs.com/vss_base/python:3.12-slim

# 定义构建参数
ARG APT_MIRROR=mirrors.aliyun.com
ARG PIP_MIRROR_URL=https://mirrors.aliyun.com/pypi/simple/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# --- 1. 系统依赖 (换源 + 安装) ---
RUN sed -i "s|deb.debian.org|$APT_MIRROR|g" /etc/apt/sources.list.d/debian.sources && \
    sed -i "s|security.debian.org|$APT_MIRROR|g" /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg gcc libpq-dev fonts-wqy-zenhei \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- 2. 全局 PIP 配置 (关键防超时) ---
RUN pip config set global.index-url $PIP_MIRROR_URL && \
    pip config set global.timeout 1000

# --- 3. 离线安装 PyTorch (防 GPU 版臃肿) ---
COPY local_packages/ /tmp/packages/
RUN pip install --no-cache-dir /tmp/packages/torch-*.whl /tmp/packages/torchvision-*.whl && \
    rm -rf /tmp/packages

# --- 4. 安装业务依赖 ---
COPY requirements.base.txt .
COPY requirements.media.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.media.txt

# --- 5. 复制代码 (注意 .dockerignore) ---
COPY . .

# 权限设置
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

CMD ["celery", "-A", "visify_ssw", "worker", "-l", "info"]
3. .dockerignore 检查清单
确保以下目录被忽略，防止镜像膨胀：

Plaintext

local_packages/
local_models/
media/
data/
.git/
__pycache__/
.env
🚢 第四阶段：部署运行
在 Ubuntu Edge Server 上运行容器时，使用 -v 挂载大文件。

Bash

docker run -d \
  --name vss_workbench \
  --restart unless-stopped \
  # 1. 挂载模型文件 (替代 COPY)
  -v /home/wzhang/models/local_models:/app/local_models \
  # 2. 挂载数据/日志目录
  -v /www/data:/app/media \
  -v /www/logs:/app/logs \
  # 3. 挂载配置 (可选)
  -v /home/wzhang/config/.env:/app/.env \
  -p 8000:8000 \
  10.168.1.31:5000/vss_edge/workbench:v1.4.1-slim
🧹 附录：运维与清理 Cheatsheet
1. 磁盘空间急救 如果 docker push 再次出现 EOF，检查服务端空间：

Bash

# 检查根目录大文件夹
sudo du -h --max-depth=1 / | sort -hr

# 清理 Docker 悬空镜像
docker system prune -f

# 清理 Registry 失败的上传碎片 (在挂载目录)
rm -rf .../repositories/vss_edge/workbench/_uploads
2. 验证网络连通性

Bash

# 测试国内速度
ping mirrors.aliyun.com

# 测试 VPN 连通性 (需宿主机开启 VPN)
curl -I https://storage.googleapis.com