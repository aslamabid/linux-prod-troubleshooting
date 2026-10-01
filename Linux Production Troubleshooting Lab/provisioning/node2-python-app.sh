#!/usr/bin/env bash
# Run on node2. Deploys the Flask app and points it at node3's Postgres.
# Usage: sudo bash node2-python-app.sh <node3-ip>
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run as root: sudo bash node2-python-app.sh <node3-ip>" >&2
  exit 1
fi

NODE3_IP="${1:?Usage: node2-python-app.sh <node3-ip>}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_SRC="${SCRIPT_DIR}/../apps/python-app"

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip

id -u labapp &>/dev/null || useradd --system --create-home --shell /usr/sbin/nologin labapp

mkdir -p /opt/lab/python-app
cp "${APP_SRC}/app.py" "${APP_SRC}/requirements.txt" /opt/lab/python-app/

cat >/opt/lab/python-app/.env <<EOF
DB_HOST=${NODE3_IP}
DB_NAME=labdb
DB_USER=labuser
DB_PASSWORD=labpass
EOF

python3 -m venv /opt/lab/python-app/venv
/opt/lab/python-app/venv/bin/pip install --upgrade pip
/opt/lab/python-app/venv/bin/pip install -r /opt/lab/python-app/requirements.txt

chown -R labapp:labapp /opt/lab/python-app
chmod 600 /opt/lab/python-app/.env

cp "${APP_SRC}/python-app.service" /etc/systemd/system/python-app.service
systemctl daemon-reload
systemctl enable --now python-app
systemctl restart python-app

echo "==> python-app running on :8000, DB_HOST=${NODE3_IP}"
echo "==> Test with: curl http://localhost:8000/health"
echo "==> journalctl -u python-app -f   # to tail logs"
