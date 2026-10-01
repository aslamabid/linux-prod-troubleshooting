# 00 — Lab Setup (KodeKloud playground)

## 1. Launch the playground

1. Log into KodeKloud → **Playgrounds** → launch a generic multi-VM Linux
   playground (plain Ubuntu servers with root/sudo, reachable from each other
   over a private network).
2. KodeKloud playgrounds cap out at **3 VMs at a time**, so this lab runs on
   3 nodes instead of 4 — the monitoring stack is co-located on node1
   alongside nginx (the lightest-weight role) rather than getting its own VM.
3. Note down the private IP of each VM (`ip a` or `hostname -I` on each one)
   and assign roles:

   | Role                      | IP (fill in) |
   |---------------------------|--------------|
   | node1 (nginx + monitoring)|              |
   | node2 (app)               |              |
   | node3 (db)                |              |

   Keep this table handy — you'll paste these IPs into the Prometheus config
   and into the python app's DB connection string.

## 2. Copy the repo to each VM

The playground terminal is browser-based, so the simplest path is to `git
clone` this repo onto **each** VM (or `scp`/paste script contents manually if
the VMs have no outbound internet access to your git remote).

```bash
# on every VM
sudo apt-get update -y
sudo apt-get install -y git
git clone <your-fork-or-repo-url> lab
cd lab
```

If the playground has no internet egress at all, copy each script's contents
directly (select-all/copy in your editor, paste into a file created with
`nano`/`vi` on the VM).

## 3. Run common provisioning everywhere

On **all 3 VMs**:

```bash
sudo bash provisioning/common.sh
```

This installs the shared troubleshooting toolbox (`htop`, `iotop`, `sysstat`,
`strace`, `ltrace`, `lsof`, `tcpdump`, `dnsutils`, `iproute2`, `net-tools`,
`nmap`, `stress-ng`, `fio`, `curl`, `jq`) and `node_exporter` (so node1's
Prometheus can scrape it later).

## 4. Run the role-specific script(s)

- On **node1**: `sudo bash provisioning/node1-nginx.sh <node2-ip>`, then
  `sudo bash provisioning/node4-monitoring.sh <node2-ip> <node3-ip>`
- On **node2**: `sudo bash provisioning/node2-python-app.sh <node3-ip>`
- On **node3**: `sudo bash provisioning/node3-database.sh`

Each script prints a summary of what it configured and which ports are open.

## 5. Wire up monitoring

`node4-monitoring.sh` (run on node1) templates `monitoring/prometheus.yml`
with node1 scraped via `localhost` and node2/node3 scraped via the IPs you
passed in, then starts Prometheus + Grafana + Alertmanager. Confirm:

- Prometheus targets page: `http://<node1-ip>:9090/targets` — all 3
  `node_exporter` targets (and the app's own metrics if exposed) should be
  **UP**.
- Grafana: `http://<node1-ip>:3000` (default `admin`/`admin`) — the
  Prometheus datasource is auto-provisioned; import dashboard ID `1860`
  (Node Exporter Full) to get CPU/mem/disk/net panels per node.

## 6. Smoke test the app path

```bash
curl http://<node1-ip>/           # nginx -> proxies to node2 python app
curl http://<node1-ip>/health     # python app health check
curl http://<node1-ip>/db-check   # python app -> postgres on node3
```

All three should return `200 OK`. If not, this is itself a great first
troubleshooting exercise (check nginx config, `systemctl status python-app`,
`ss -tlnp`, Postgres `pg_hba.conf`/firewall) before moving on to the
intentional-breakage scenarios.

## 7. Reset between scenarios

Most scenarios include a "cleanup" step. If a VM gets into a state you can't
recover (e.g. genuinely OOM-locked), the fastest fix in a playground is
usually to just terminate/relaunch that one VM and re-run its provisioning
script — that's normal and part of the learning loop, not a failure.
