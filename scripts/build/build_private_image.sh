# 0. 登录阿里云 (如果尚未登录)
#docker login "${REGISTRY}"
#建议构建私有化仓库时，挂载第三方镜像加速缓存，比如轩辕镜像

# 1. 定义变量
REGISTRY="crpi-34v4qt829vtet2cy.cn-hangzhou.personal.cr.aliyuncs.com"
NAMESPACE="vss_base"
TARGET_PREFIX="${REGISTRY}/${NAMESPACE}"

# 2. 搬运Python的基础镜像
docker pull python:3.12-slim
docker tag python:3.12-slim "${TARGET_PREFIX}/python:3.12-slim"
docker push "${TARGET_PREFIX}/python:3.12-slim"

# 3. 搬运 Postgres
docker pull postgres:16-alpine
docker tag postgres:16-alpine "${TARGET_PREFIX}/postgres:16-alpine"
docker push "${TARGET_PREFIX}/postgres:16-alpine"

# 4. 搬运 Redis
docker pull redis:7-alpine
docker tag redis:7-alpine "${TARGET_PREFIX}/redis:7-alpine"
docker push "${TARGET_PREFIX}/redis:7-alpine"

# 5. 搬运 Nginx
docker pull nginx:1.25-alpine
docker tag nginx:1.25-alpine "${TARGET_PREFIX}/nginx:1.25-alpine"
docker push "${TARGET_PREFIX}/nginx:1.25-alpine"

# 6. 搬运 Node
docker pull node:20-alpine
docker tag node:20-alpine "${TARGET_PREFIX}/node:20-alpine"
docker push "${TARGET_PREFIX}/node:20-alpine"

# 7. 搬运 Label Studio
docker pull heartexlabs/label-studio:latest
docker tag heartexlabs/label-studio:latest "${TARGET_PREFIX}/label-studio:latest"
docker push "${TARGET_PREFIX}/label-studio:latest"