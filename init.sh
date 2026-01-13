#!/bin/bash
# init.sh: Single-entry initialization and deployment script for VSS Edge.
# 修正版V10：最终健壮版，修复CORS变量替换问题，集成自动端口推导。

# 严格退出 on error
set -e

# --- Phase 1: Configuration Generation & Global Logging ---

# 定义日志文件和时间戳
LOG_TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
GLOBAL_LOG_FILE="deployment_log_${LOG_TIMESTAMP}.log"

# 将后续所有输出重定向到日志文件，并同时输出到终端 (tee)
exec > >(tee -a "$GLOBAL_LOG_FILE") 2>&1

echo "================================================"
echo "Visify Story Studio - Initialization and Deployment"
echo "Log file: $GLOBAL_LOG_FILE"
echo "================================================"

# --- Configuration Variables ---
ENV_TEMPLATE_FILE=".env.template"
ENV_FILE=".env"

# Docker Compose 文件
BASE_COMPOSE_FILE="docker-compose.base.yml"
DEPLOY_COMPOSE_FILE="docker-compose.test.yml"

# Nginx 配置文件 (必须存在，用于卷挂载)
NGINX_MEDIA_CONF="configs/nginx/vss-media-server.conf"

# 必需的 volumes 目录
REQUIRED_DIRS=("media_root" "staticfiles" "configs/nginx")

# --- Helper Functions ---
generate_secret() {
    openssl rand -hex 32
}

# --- 关键前置检查函数 ---
check_file_exists() {
    FILE=$1
    if [ ! -f "$FILE" ]; then
        echo "❌ 错误: 关键文件 '$FILE' 未找到。请确保该文件位于正确位置。"
        exit 1
    fi
}

# --- Configuration Main Logic ---
echo "Visify Story Studio - Deployment Initializer"
echo "------------------------------------------------"

# 1. 检查所有必需的配置文件
check_file_exists "$ENV_TEMPLATE_FILE"
check_file_exists "$BASE_COMPOSE_FILE"
check_file_exists "$DEPLOY_COMPOSE_FILE"
check_file_exists "$NGINX_MEDIA_CONF"

# 2. 处理 .env 文件
if [ -f "$ENV_FILE" ]; then
    read -p "Warning: '$ENV_FILE' already exists. Do you want to overwrite it? [y/N]: " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo "Aborted."
        exit 0
    fi
fi

echo "Generating new '$ENV_FILE' from template..."
cp "$ENV_TEMPLATE_FILE" "$ENV_FILE"

echo "Generating secure keys..."
DJANGO_SECRET_KEY=$(generate_secret)
POSTGRES_PASSWORD=$(generate_secret)

sed -i.bak "s|DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}|" "$ENV_FILE"
sed -i.bak "s|POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${POSTGRES_PASSWORD}|" "$ENV_FILE"

echo "Please provide initial settings for the instance:"

# --- Prompt for the Public Endpoint ---
# 1. 获取核心入口 (用户唯一需要输入的参数)
read -p "Enter the Public Endpoint URL (e.g., http://192.168.1.X): " PUBLIC_ENDPOINT

# 去除可能存在的末尾斜杠
PUBLIC_ENDPOINT=${PUBLIC_ENDPOINT%/}

# 2. 智能提取协议和主机名
URL_SCHEME=$(echo "$PUBLIC_ENDPOINT" | grep -oE "^https?") || URL_SCHEME="http"
CURRENT_HOST=$(echo "$PUBLIC_ENDPOINT" | sed -E 's|https?://||' | sed -E 's|:[0-9]+.*||' | sed 's|/.*||')

echo "------------------------------------------------"
echo "Auto-configuring Service Endpoints based on: $CURRENT_HOST"
echo "------------------------------------------------"

# 3. 定义安全端口 (80XX 策略)
PORT_MEDIA=9999

# 4. 自动构建派生 URL
LOCAL_MEDIA_URL_BASE="${URL_SCHEME}://${CURRENT_HOST}:${PORT_MEDIA}"

echo "-> Django Admin:      ${PUBLIC_ENDPOINT}:8000"
echo "-> Local Media:       ${LOCAL_MEDIA_URL_BASE}"

# 5. 写入 .env
# 更新/写入 PUBLIC_ENDPOINT
if grep -q "PUBLIC_ENDPOINT=" "$ENV_FILE"; then
    sed -i.bak "s|PUBLIC_ENDPOINT=.*|PUBLIC_ENDPOINT=${PUBLIC_ENDPOINT}|" "$ENV_FILE"
else
    echo "PUBLIC_ENDPOINT=${PUBLIC_ENDPOINT}" >> "$ENV_FILE"
fi

# 写入 LOCAL_MEDIA_URL_BASE
sed -i.bak '/^LOCAL_MEDIA_URL_BASE=/d' "$ENV_FILE"
echo "LOCAL_MEDIA_URL_BASE=${LOCAL_MEDIA_URL_BASE}" >> "$ENV_FILE"

# 清理备份文件
rm -f "${ENV_FILE}.bak"

# --- Other prompts ---
read -p "Enter the initial Django superuser email: " DJANGO_SUPERUSER_EMAIL
read -s -p "Enter the initial Django superuser password: " DJANGO_SUPERUSER_PASSWORD
echo

# [新增] Cloud API 交互配置模块
echo
echo "--- Cloud API Configuration (VSS-Cloud) ---"
echo "Please enter the connection details for the Cloud Orchestrator."
read -p "Cloud API Base URL (e.g., http://cloud.example.com:8000): " CLOUD_API_BASE_URL
read -p "Cloud Instance ID (Your Edge unique ID): " CLOUD_INSTANCE_ID
read -p "Cloud API Key: " CLOUD_API_KEY
echo

HOSTNAME=$CURRENT_HOST
DEFAULT_ALLOWED_HOSTS="localhost,127.0.0.1,${HOSTNAME}"
read -p "Enter comma-separated Allowed Hosts [${DEFAULT_ALLOWED_HOSTS}]: " DJANGO_ALLOWED_HOSTS
DJANGO_ALLOWED_HOSTS=${DJANGO_ALLOWED_HOSTS:-$DEFAULT_ALLOWED_HOSTS}

# Use sed to replace placeholders
sed -i.bak "s|DJANGO_SUPERUSER_EMAIL=.*|DJANGO_SUPERUSER_EMAIL=\"${DJANGO_SUPERUSER_EMAIL}\"|" "$ENV_FILE"
sed -i.bak "s|DJANGO_SUPERUSER_PASSWORD=.*|DJANGO_SUPERUSER_PASSWORD=\"${DJANGO_SUPERUSER_PASSWORD}\"|" "$ENV_FILE"
sed -i.bak "s|DJANGO_ALLOWED_HOSTS=.*|DJANGO_ALLOWED_HOSTS=\"${DJANGO_ALLOWED_HOSTS}\"|" "$ENV_FILE"

chmod 600 "$ENV_FILE"

echo "Creating necessary directories..."
for dir in "${REQUIRED_DIRS[@]}"; do
    mkdir -p "$dir"
    chmod -R 777 "$dir"
done

echo "✅ Configuration successful. Starting deployment..."

# --- Phase 2: Deployment ---
COMPOSE_FILES="-f $BASE_COMPOSE_FILE -f $DEPLOY_COMPOSE_FILE"
WEB_SERVICE="web"
DB_SERVICE="db"
PROJECT_NAME="vss-edge"
COLLECTSTATIC_LOG_FILE="exec_tmp.log"

echo "1. Bringing up all Docker services..."
docker compose -p $PROJECT_NAME $COMPOSE_FILES up -d

if [ $? -ne 0 ]; then
    echo "❌ 错误: Docker Compose 启动服务失败。"
    exit 1
fi

echo "1.1 配置文件已通过卷挂载实现。"
echo "1.2 Nginx 服务已通过卷挂载加载配置。"

echo "2. 等待服务就绪..."
sleep 5
MAX_RETRIES=10
RETRY_COUNT=0

echo "正在等待 PostgreSQL 数据库容器 ($DB_SERVICE) 就绪..."
until [ $RETRY_COUNT -ge $MAX_RETRIES ]
do
    if docker compose -p $PROJECT_NAME $COMPOSE_FILES exec $DB_SERVICE pg_isready -q; then
        echo "✅ 数据库已就绪！"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT+1))
    echo "   数据库未就绪，重试 $RETRY_COUNT/$MAX_RETRIES..."
    sleep 5
done

if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
    echo "❌ 错误: 数据库未在规定时间内就绪，终止部署。"
    exit 1
fi

echo "3. 执行数据库迁移 (Migrate)..."
if ! docker compose -p $PROJECT_NAME $COMPOSE_FILES exec $WEB_SERVICE python manage.py migrate --noinput > "$COLLECTSTATIC_LOG_FILE" 2>&1; then
    echo "❌ 错误: 数据库迁移失败！"
    cat "$COLLECTSTATIC_LOG_FILE"
    exit 1
fi
echo "✅ 迁移成功完成。"

echo "4. 执行自动化配置 (setup_instance)..."
docker compose -p $PROJECT_NAME $COMPOSE_FILES exec $WEB_SERVICE python manage.py setup_instance \
    --cloud-url="$CLOUD_API_BASE_URL" \
    --cloud-id="$CLOUD_INSTANCE_ID" \
    --cloud-key="$CLOUD_API_KEY" > "$COLLECTSTATIC_LOG_FILE" 2>&1
SETUP_INSTANCE_EXIT_CODE=$?
cat "$COLLECTSTATIC_LOG_FILE"

if [ $SETUP_INSTANCE_EXIT_CODE -ne 0 ]; then
    echo "❌ 错误: setup_instance 失败！"
    exit 1
fi
echo "✅ 自动化配置成功完成。"

echo "5. 收集静态文件 (collectstatic)..."
if ! docker compose -p $PROJECT_NAME $COMPOSE_FILES exec $WEB_SERVICE python manage.py collectstatic --noinput > "$COLLECTSTATIC_LOG_FILE" 2>&1; then
    echo "❌ 错误: collectstatic 失败！"
    cat "$COLLECTSTATIC_LOG_FILE"
    exit 1
fi
echo "✅ 静态文件收集成功完成。"
rm "$COLLECTSTATIC_LOG_FILE" 2>/dev/null

echo "================================================"
echo "--- ✅ 部署完成 ---"
echo "日志文件已保存到 $GLOBAL_LOG_FILE"
echo "================================================"