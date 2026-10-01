#!/usr/bin/env bash
# Shared provisioning: run on every node (node1, node2, node3, monitoring).
# Installs the troubleshooting toolbox + node_exporter for metrics scraping.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run as root: sudo bash common.sh" >&2
  exit 1
fi

echo "==> Updating apt and installing troubleshooting toolbox..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y \
  htop iotop sysstat \
  strace ltrace lsof \
  tcpdump dnsutils iproute2 net-tools nmap \
  stress-ng fio \
  curl wget jq git vim \
  prometheus-node-exporter \
  lm-sensors psmisc

echo "==> Enabling sysstat data collection (sar history)..."
sed -i 's/^ENABLED="false"/ENABLED="true"/' /etc/default/sysstat 2>/dev/null || true
systemctl enable --now sysstat 2>/dev/null || true

echo "==> Enabling node_exporter (metrics on :9100)..."
systemctl enable --now prometheus-node-exporter

echo "==> Raising open-file limits (useful for the 'too many connections' scenario)..."
cat >/etc/security/limits.d/99-lab.conf <<'EOF'
*    soft nofile 65535
*    hard nofile 65535
root soft nofile 65535
root hard nofile 65535
EOF

echo "==> common.sh done. node_exporter listening on :9100."
hostname -I
