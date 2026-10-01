#!/usr/bin/env bash
# Run on node1. Installs nginx as a reverse proxy in front of node2's app.
# Usage: sudo bash node1-nginx.sh <node2-ip>
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run as root: sudo bash node1-nginx.sh <node2-ip>" >&2
  exit 1
fi

NODE2_IP="${1:?Usage: node1-nginx.sh <node2-ip>}"

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y nginx

cat >/etc/nginx/sites-available/lab-app <<EOF
upstream lab_app {
    server ${NODE2_IP}:8000;
}

server {
    listen 80 default_server;
    server_name _;

    location / {
        proxy_pass http://lab_app;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_connect_timeout 5s;
        proxy_read_timeout 30s;
    }
}
EOF

ln -sf /etc/nginx/sites-available/lab-app /etc/nginx/sites-enabled/lab-app
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable --now nginx
systemctl reload nginx

echo "==> nginx configured, proxying / -> ${NODE2_IP}:8000"
echo "==> Test with: curl http://<this-node-ip>/health"
