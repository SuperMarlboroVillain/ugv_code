#!/bin/bash
# UGV 扫图防死机系统加固 —— 需要 root：sudo bash ~/harden_ugv.sh
set -e

echo '== 1/3 创建 4GB NVMe swapfile（优先级低于 zram，仅作兜底）=='
if swapon --show=NAME | grep -q '^/swapfile'; then
  echo 'swapfile 已存在，跳过'
else
  fallocate -l 4G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon --priority 10 /swapfile
  echo '/swapfile none swap sw,pri=10 0 0' >> /etc/fstab
fi

echo '== 2/3 内存策略：更积极使用 swap（zram 场景推荐值）=='
cat > /etc/sysctl.d/99-ugv-mem.conf <<'EOF'
vm.swappiness=100
vm.page-cluster=0
EOF
sysctl --system >/dev/null

echo '== 3/3 安装 earlyoom：内存耗尽前杀掉最大进程，避免整机死机 =='
apt-get update -qq
apt-get install -y earlyoom
systemctl enable --now earlyoom

echo '== 完成 =='
free -h
swapon --show
