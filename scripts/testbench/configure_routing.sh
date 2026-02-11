#!/bin/bash
# 03_config_routing_fixed.sh
# 修正版：适配 enp0s3=Bridge, enp0s8=NAT 的情况

echo ">>> 检测到 enp0s8 处于 DOWN 状态，正在配置路由规则..."

# 根据您的 ip a 结果指定的接口名称
IF_BRIDGE="enp0s3"  # 也就是目前的 10.168.1.186
IF_NAT="enp0s8"     # 目前 DOWN 的那个

cat <<EOF | sudo tee /etc/netplan/99-custom-routing.yaml
network:
  version: 2
  renderer: networkd
  ethernets:
    $IF_NAT:
      dhcp4: true
      dhcp4-overrides:
        route-metric: 100  # 优先级高：去 Google/公网 走 NAT (enp0s8)
    $IF_BRIDGE:
      dhcp4: true
      dhcp4-overrides:
        route-metric: 200  # 优先级低：仅局域网互访 走 Bridge (enp0s3)
EOF

# 修改权限并应用
sudo chmod 600 /etc/netplan/99-custom-routing.yaml

echo ">>> 正在应用网络配置（可能需要几秒钟）..."
sudo netplan apply

echo ">>> 验证结果："
echo "1. 检查 enp0s8 是否已有 IP (应为 10.0.2.x):"
ip a show $IF_NAT
echo "--------------------------------"
echo "2. 检查默认路由 (Metric 100 应指向 $IF_NAT):"
ip route | grep default