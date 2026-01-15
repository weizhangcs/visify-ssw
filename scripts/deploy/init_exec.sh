#!/bin/bash
# 文件路径: D:/DevProjects/PyCharmProjects/visify-ssw/init_exec.sh
# 描述: 执行部署流程 (Docker Up -> Migrate -> Setup Instance)

set -e

# [关键] 切换到项目根目录 (因为脚本现在位于 scripts/ 子目录)
cd "$(dirname "$0")/.." || exit 1

# 日志记录
LOG_TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
EXEC_LOG_FILE="install_exec_${LOG_TIMESTAMP}.log"
exec > >(tee -a "$EXEC_LOG_FILE") 2>&1

echo "================================================"
echo "🚀 VSS Edge - 开始部署执行"
echo "日志文件: $EXEC_LOG_FILE"
echo "================================================"

if [ ! -f ".env" ]; then
    echo "❌ 错误: 未找到 .env 配置文件。"
    echo "   请先运行 ./init_setup.sh 生成配置。"
    exit 1
fi

# 加载 .env 变量 (以便获取 SETUP_CLOUD_* 变量)
# set -a 自动导出变量
set -a
source .env
set +a

# 定义常量
BASE_COMPOSE_FILE="docker-compose.base.yml"
DEPLOY_COMPOSE_FILE="docker-compose.test.yml"
COMPOSE_FILES="-f $BASE_COMPOSE_FILE -f $DEPLOY_COMPOSE_FILE"
PROJECT_NAME="vss-edge"
WEB_SERVICE="web"
DB_SERVICE="db"

echo "1. 启动 Docker 服务..."
docker compose -p $PROJECT_NAME $COMPOSE_FILES up -d

if [ $? -ne 0 ]; then
    echo "❌ 错误: Docker Compose 启动失败。"
    exit 1
fi

echo "2. 等待数据库就绪..."
MAX_RETRIES=30
RETRY_COUNT=0
until [ $RETRY_COUNT -ge $MAX_RETRIES ]
do
    if docker compose -p $PROJECT_NAME $COMPOSE_FILES exec $DB_SERVICE pg_isready -q; then
        echo "✅ 数据库已连接。"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT+1))
    echo "   等待数据库... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
done

if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
    echo "❌ 错误: 数据库启动超时。"
    exit 1
fi

echo "3. 执行数据库迁移 (Migrate)..."
docker compose -p $PROJECT_NAME $COMPOSE_FILES exec $WEB_SERVICE python manage.py migrate --noinput

echo "4. 执行实例初始化 (Setup Instance)..."
# 使用从 .env 加载的 SETUP_ 变量
docker compose -p $PROJECT_NAME $COMPOSE_FILES exec $WEB_SERVICE python manage.py setup_instance \
    --cloud-url="${SETUP_CLOUD_API_BASE_URL}" \
    --cloud-id="${SETUP_CLOUD_INSTANCE_ID}" \
    --cloud-key="${SETUP_CLOUD_API_KEY}"

echo "5. 收集静态文件 (Collectstatic)..."
docker compose -p $PROJECT_NAME $COMPOSE_FILES exec $WEB_SERVICE python manage.py collectstatic --noinput

echo "================================================"
echo "✅✅✅ 部署全部完成！"
echo "访问地址: ${PUBLIC_ENDPOINT}"
echo "后台管理: ${PUBLIC_ENDPOINT}:8000/admin/"
echo "================================================"