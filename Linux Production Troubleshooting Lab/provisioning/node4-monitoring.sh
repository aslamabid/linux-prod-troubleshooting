#!/usr/bin/env bash
# Run on node1, AFTER node1-nginx.sh (KodeKloud playgrounds cap out at 3 VMs,
# so monitoring is co-located on node1 instead of a dedicated 4th VM).
# Installs Prometheus + Alertmanager (from Ubuntu apt) and Grafana (from
# Grafana's official apt repo), then wires up scraping of node1 itself
# (localhost) plus node2 and node3's node_exporter.
# Usage: sudo bash node4-monitoring.sh <node2-ip> <node3-ip>
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run as root: sudo bash node4-monitoring.sh <node2-ip> <node3-ip>" >&2
  exit 1
fi

NODE2_IP="${1:?Usage: node4-monitoring.sh <node2-ip> <node3-ip>}"
NODE3_IP="${2:?Usage: node4-monitoring.sh <node2-ip> <node3-ip>}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MON_SRC="monitoring"

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y prometheus prometheus-alertmanager apt-transport-https software-properties-common gnupg curl

# --- Grafana (official apt repo; not in default Ubuntu repos) ---
if ! command -v grafana-server &>/dev/null; then
  curl -fsSL https://apt.grafana.com/gpg.key | gpg --dearmor -o /etc/apt/keyrings/grafana.gpg
  echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" \
    > /etc/apt/sources.list.d/grafana.list
  apt-get update -y
  apt-get install -y grafana
fi

# --- Prometheus scrape config (node1 is scraped via localhost since co-located) ---
sed -e "s/__NODE2_IP__/${NODE2_IP}/g" \
    -e "s/__NODE3_IP__/${NODE3_IP}/g" \
    "${MON_SRC}/prometheus.yml" > /etc/prometheus/prometheus.yml

# --- Grafana datasource provisioning ---
mkdir -p /etc/grafana/provisioning/datasources
cp "${MON_SRC}/grafana-datasource.yml" /etc/grafana/provisioning/datasources/prometheus.yml

systemctl enable --now prometheus-node-exporter 2>/dev/null || true
systemctl enable --now prometheus
systemctl enable --now prometheus-alertmanager
systemctl enable --now grafana-server
systemctl restart prometheus grafana-server

echo "==> Prometheus:   http://<this-node-ip>:9090/targets"
echo "==> Grafana:      http://<this-node-ip>:3000  (admin/admin, change on first login)"
echo "==> Import dashboard ID 1860 (Node Exporter Full) once logged in."
