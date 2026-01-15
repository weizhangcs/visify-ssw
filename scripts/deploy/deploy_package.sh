#!/bin/bash
# 文件路径: scripts/deploy_package.sh
# 描述: VSS Edge 部署包构建工具
# 运行: ./scripts/deploy_package.sh

set -e

# --- 1. 跨平台路径解析与环境准备 ---
# 适配 macOS/Linux 的 readlink 差异
if [[ "$(uname)" == "Darwin" ]]; then
    READLINK="greadlink"
    if ! command -v $READLINK &> /dev/null; then
        echo "[ERROR] MacOS 需要安装 coreutils (brew install coreutils)"
        exit 1
    fi
else
    READLINK="readlink"
fi

# 获取脚本所在目录的绝对路径，并推导项目根目录
SCRIPT_DIR=$($READLINK -f "$(dirname "${BASH_SOURCE[0]}")")
PROJECT_ROOT=$(dirname "$SCRIPT_DIR")

# 切换到项目根目录
cd "$PROJECT_ROOT" || { echo "[ERROR] 无法进入项目根目录: $PROJECT_ROOT"; exit 1; }
echo "[INFO] 工作目录: $(pwd)"

# --- 2. 配置变量 ---
APP_NAME="vss-edge"
# 获取 Git Hash，如果不是 git 仓库则使用 nogit
GIT_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "nogit")
VERSION="$(date +%Y%m%d)-${GIT_HASH}"

OUTPUT_DIR="dist"
PACKAGE_NAME="${APP_NAME}-deploy-${VERSION}"
TAR_FILE="${PACKAGE_NAME}.tar.gz"
TEMP_DIR="${OUTPUT_DIR}/${PACKAGE_NAME}"

# --- 3. 定义交付物清单 (Manifest) ---
# 使用白名单模式，明确指定需要打包的文件/目录
# 注意：这里保留 scripts 目录结构，不进行扁平化，以配合脚本内的相对路径逻辑
FILES_TO_INCLUDE=(
    "scripts"
    "configs"
    ".env.template"
    "docker-compose.base.yml"
    "docker-compose.test.yml"
)

# --- 4. 清理与初始化 ---
echo "[INFO] 开始构建部署包: ${TAR_FILE}"

# 清理旧构建
rm -rf "$TEMP_DIR"
mkdir -p "$TEMP_DIR"

# --- 5. 复制文件 ---
echo "[INFO] 正在复制文件..."
MISSING_CRITICAL=0

for item in "${FILES_TO_INCLUDE[@]}"; do
    if [ -e "$item" ]; then
        # 使用 cp -r 递归复制，保留目录结构
        # --parents 选项在 macOS 上非标准，这里直接复制到 TEMP_DIR 即可保持相对路径
        cp -R "$item" "$TEMP_DIR/"
        echo "   -> Included: $item"
    else
        echo "[WARN] ⚠️  文件或目录 '$item' 未找到！"
        MISSING_CRITICAL=1
    fi
done

if [ $MISSING_CRITICAL -eq 1 ]; then
    echo "[ERROR] 无法继续，缺失核心依赖文件！"
    exit 1
fi

# 确保脚本具有执行权限
chmod +x "$TEMP_DIR/scripts/"*.sh

# --- 6. 生成部署说明 (DEPLOY_NOTES) ---
echo "[INFO] 生成部署说明..."
cat > "$TEMP_DIR/DEPLOY_NOTES.txt" <<EOF
VSS Edge Deployment Package
---------------------------
Version: ${VERSION}
Built at: $(date)
Git Hash: ${GIT_HASH}

部署步骤:
1. 解压安装包:
   tar -zxvf ${TAR_FILE}

2. 进入目录:
   cd ${PACKAGE_NAME}

3. 环境准备 (仅首次):
   sudo ./scripts/install_deps.sh
   (执行后建议退出重登或执行 newgrp docker)

4. 初始化配置 (交互式):
   ./scripts/init_setup.sh

5. 启动部署:
   ./scripts/init_exec.sh

注意:
- 配置文件位于 .env (由 init_setup.sh 生成)
- 默认端口: 8000 (Web), 9999 (Media)
EOF

# --- 7. 打包 (Tar) ---
echo "[INFO] 正在压缩..."
cd "$OUTPUT_DIR" || exit 1

# 兼容性打包命令
if [[ "$(uname)" == "Darwin" ]]; then
    # macOS (BSD tar)
    tar -czf "${TAR_FILE}" --exclude ".*" "${PACKAGE_NAME}"
else
    # Linux (GNU tar) - 强制归属 root，避免带入开发机的用户 ID
    tar -czf "${TAR_FILE}" --owner=0 --group=0 --exclude ".*" "${PACKAGE_NAME}"
fi

# --- 8. 结果校验 ---
if [ -f "${TAR_FILE}" ]; then
    # 计算大小
    if [[ "$(uname)" == "Darwin" ]]; then
        FILE_SIZE=$(du -h "${TAR_FILE}" | awk '{print $1}')
    else
        FILE_SIZE=$(du -h "${TAR_FILE}" | cut -f1)
    fi

    # 清理临时目录
    rm -rf "${PACKAGE_NAME}"

    echo "========================================"
    echo "✅ 构建成功！"
    echo "📂 文件位置: ${OUTPUT_DIR}/${TAR_FILE}"
    echo "📦 文件大小: ${FILE_SIZE}"
    echo "========================================"
else
    echo "[ERROR] 打包失败。"
    exit 1
fi