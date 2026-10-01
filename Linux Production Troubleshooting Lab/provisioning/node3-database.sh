#!/usr/bin/env bash
# Run on node3. Installs Postgres and creates the lab database/user.
# Usage: sudo bash node3-database.sh
#
# By default only RFC1918 private ranges may connect (this is a lab, but we
# still avoid a blanket 0.0.0.0/0 listen-everyone rule out of habit).
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run as root: sudo bash node3-database.sh" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y postgresql

systemctl enable --now postgresql

PG_VERSION="$(psql --version | grep -oP '\d+' | head -1)"
PG_CONF_DIR="/etc/postgresql/${PG_VERSION}/main"

sudo -u postgres psql -c "SELECT 1 FROM pg_roles WHERE rolname='labuser'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE USER labuser WITH PASSWORD 'labpass';"

sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='labdb'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE DATABASE labdb OWNER labuser;"

sed -i "s/^#\?listen_addresses.*/listen_addresses = '*'/" "${PG_CONF_DIR}/postgresql.conf"

for cidr in "10.0.0.0/8" "172.16.0.0/12" "192.168.0.0/16"; do
  grep -q "$cidr" "${PG_CONF_DIR}/pg_hba.conf" || \
    echo "host    all             all             ${cidr}            md5" >> "${PG_CONF_DIR}/pg_hba.conf"
done

systemctl restart postgresql

pg_isready

echo "==> Postgres ready: db=labdb user=labuser (listening on :5432)"
echo "==> Test locally with: sudo -u postgres psql -d labdb -c 'select 1;'"
