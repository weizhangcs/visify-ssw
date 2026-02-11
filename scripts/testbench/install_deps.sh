#!/bin/bash
# 文件路径: install_deps_fixed.sh
# 描述: VSS Cloud 服务器环境初始化脚本 (修正优化版)
# 适配: Ubuntu 24.04 LTS (DEB822格式源), Debian 12 LTS
# 修复: Docker GPG路径适配, Ubuntu 24.04 源冲突问题

set -e

# --- 颜色定义 ---
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO] $1${NC}"; }
log_warn() { echo -e "${YELLOW}[WARN] $1${NC}"; }
log_err() { echo -e "${RED}[ERROR] $1${NC}"; exit 1; }

# --- 默认配置 ---
SOURCE_TYPE="overseas"
TARGET_OS="auto"
ALIYUN_BASE="https://mirrors.aliyun.com"

# --- 参数解析 ---
parse_params() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --cn) SOURCE_TYPE="cn"; shift ;;
            --os)
                if [[ "$2" =~ ^(ubuntu|debian)$ ]]; then
                    TARGET_OS="$2"; shift 2
                else
                    log_err "无效的OS参数: $2，仅支持 ubuntu/debian"
                fi
                ;;
            --help|-h)
                echo "使用帮助: sudo ./install_deps.sh [--cn] [--os ubuntu|debian]"
                exit 0
                ;;
            *) log_err "未知参数: $1" ;;
        esac
    done
}

check_root() {
    if [ "$(id -u)" != "0" ]; then
        log_err "请使用 sudo 运行此脚本！"
    fi
}

# --- 系统检测 ---
detect_os() {
    [ -f /etc/os-release ] || log_err "无法检测操作系统"
    . /etc/os-release

    # 强制以实际系统为准，忽略错误的 --os 参数，但在参数正确时用于验证
    REAL_ID="$ID"
    if [[ "$TARGET_OS" != "auto" ]] && [[ "$TARGET_OS" != "$REAL_ID" ]]; then
        log_warn "参数指定OS ($TARGET_OS) 与实际系统 ($REAL_ID) 不符，将使用实际系统。"
    fi
    TARGET_OS="$REAL_ID"

    case $TARGET_OS in
        ubuntu)
            [[ "$VERSION_ID" != "24.04" ]] && log_warn "当前Ubuntu版本 ($VERSION_ID) 非24.04，脚本可能不兼容"
            OS_VERSION="noble"
            ;;
        debian)
            [[ "$VERSION_ID" != "12" ]] && log_warn "当前Debian版本 ($VERSION_ID) 非12，脚本可能不兼容"
            OS_VERSION="bookworm"
            ;;
        *) log_err "不支持的操作系统: $TARGET_OS" ;;
    esac
    log_info "目标环境: $TARGET_OS $OS_VERSION ($SOURCE_TYPE)"
}

# --- 核心：配置国内/国外源 ---
config_apt_repo() {
    [ "$SOURCE_TYPE" != "cn" ] && return

    log_info "正在配置阿里云镜像源..."

    if [ "$TARGET_OS" == "ubuntu" ]; then
        # 针对 Ubuntu 24.04 DEB822 格式的特殊处理
        local ubuntu_sources="/etc/apt/sources.list.d/ubuntu.sources"

        if [ -f "$ubuntu_sources" ]; then
            log_info "检测到 Ubuntu 24.04 新版源格式..."
            cp "$ubuntu_sources" "${ubuntu_sources}.bak"
            # 使用 sed 直接替换 URL，保留原文件结构，比直接覆盖更安全
            sed -i 's@http://archive.ubuntu.com/ubuntu/@http://mirrors.aliyun.com/ubuntu/@g' "$ubuntu_sources"
            sed -i 's@http://security.ubuntu.com/ubuntu/@http://mirrors.aliyun.com/ubuntu/@g' "$ubuntu_sources"
        else
            # 兼容旧版 Ubuntu 或非标准安装
            [ -f /etc/apt/sources.list ] && cp /etc/apt/sources.list /etc/apt/sources.list.bak
            cat > /etc/apt/sources.list << EOF
deb ${ALIYUN_BASE}/ubuntu/ ${OS_VERSION} main restricted universe multiverse
deb ${ALIYUN_BASE}/ubuntu/ ${OS_VERSION}-updates main restricted universe multiverse
deb ${ALIYUN_BASE}/ubuntu/ ${OS_VERSION}-backports main restricted universe multiverse
deb ${ALIYUN_BASE}/ubuntu/ ${OS_VERSION}-security main restricted universe multiverse
EOF
        fi

    elif [ "$TARGET_OS" == "debian" ]; then
        cp /etc/apt/sources.list /etc/apt/sources.list.bak
        cat > /etc/apt/sources.list << EOF
deb ${ALIYUN_BASE}/debian/ ${OS_VERSION} main contrib non-free non-free-firmware
deb ${ALIYUN_BASE}/debian/ ${OS_VERSION}-updates main contrib non-free non-free-firmware
deb ${ALIYUN_BASE}/debian/ ${OS_VERSION}-backports main contrib non-free non-free-firmware
deb http://security.debian.org/debian-security ${OS_VERSION}-security main contrib non-free non-free-firmware
EOF
    fi

    log_info "更新软件包索引..."
    apt-get update -y
}

install_dos2unix() {
    if ! command -v dos2unix &>/dev/null; then
        apt-get install -y dos2unix
    fi
}

# --- 核心：安装 Docker ---
install_docker() {
    if command -v docker &>/dev/null; then
        log_warn "Docker 已安装，跳过"
        return
    fi

    log_info "开始安装 Docker..."

    # 1. 卸载旧版本
    for pkg in docker.io docker-doc docker-compose podman-docker containerd runc; do
        apt-get remove -y $pkg 2>/dev/null || true
    done

    # 2. 安装依赖
    apt-get install -y ca-certificates curl gnupg

    # 3. 准备 GPG 密钥目录
    install -m 0755 -d /etc/apt/keyrings

    # 4. 智能选择下载源 (关键修正：URL包含 ${TARGET_OS}，且国内走阿里云)
    local gpg_url=""
    local repo_url=""

    if [ "$SOURCE_TYPE" == "cn" ]; then
        # 阿里云 GPG 及 仓库
        gpg_url="${ALIYUN_BASE}/docker-ce/linux/${TARGET_OS}/gpg"
        repo_url="${ALIYUN_BASE}/docker-ce/linux/${TARGET_OS}"
    else
        # 官方 GPG 及 仓库
        gpg_url="https://download.docker.com/linux/${TARGET_OS}/gpg"
        repo_url="https://download.docker.com/linux/${TARGET_OS}"
    fi

    log_info "下载 Docker GPG 密钥: $gpg_url"
    curl -fsSL "$gpg_url" | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    # 5. 添加 Docker 源
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] ${repo_url} \
      ${OS_VERSION} stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

    # 6. 安装
    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    systemctl enable --now docker
}

config_permission() {
    if [ -n "$SUDO_USER" ]; then
        log_info "配置用户 $SUDO_USER 权限..."
        usermod -aG docker "$SUDO_USER"
    fi
}

# --- 执行 ---
main() {
    parse_params "$@"
    check_root
    detect_os
    config_apt_repo
    install_dos2unix
    install_docker
    config_permission

    log_info "✅ 安装完成！请运行 'newgrp docker' 或重新登录以应用权限。"
}

main "$@"