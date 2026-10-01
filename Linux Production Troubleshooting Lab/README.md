# Linux Production Troubleshooting Lab

Hands-on lab for learning what happens *underneath* Linux, Kubernetes and cloud
infrastructure: process management, CPU/memory internals, filesystems,
networking, systemd, logging, disk I/O, file descriptors, namespaces and
cgroups — by deliberately breaking things and investigating them like an SRE
on call.

## Architecture

```
                        Linux Lab
                            |
          +-----------------+------------------+
          |                 |                  |
        node1             node2               node3
  (nginx + monitoring)  (python app)         (database)
          |                 |                  |
          +-----------------+------------------+
```

| Role        | What runs there                                                        |
|-------------|--------------------------------------------------------------------------|
| `node1`     | nginx reverse proxy + Prometheus, Grafana, Alertmanager, node_exporter |
| `node2`     | Python (Flask) app: CPU / memory / hang endpoints                      |
| `node3`     | PostgreSQL database                                                    |

All three roles run on **plain Ubuntu 24.04 VMs from a KodeKloud multi-VM
playground** (no local hypervisor needed). KodeKloud playgrounds cap out at
3 VMs at a time, so there's no dedicated 4th monitoring VM — instead the
monitoring stack is co-located on node1 alongside nginx, the lightest-weight
role. Each VM also runs `node_exporter` so Prometheus (on node1) can scrape
CPU/memory/disk/network metrics from all three.

## Repository layout

```
docs/                   Setup guide, cheatsheet, interview Q&A
provisioning/            One shell script per node role (run on the matching VM)
apps/python-app/         The Flask app deployed to node2
monitoring/              Prometheus + Grafana provisioning files (deployed to node1)
chaos/                   Chaos-monkey failure injector (the "advanced challenge")
scenarios/               8 break-it/investigate-it runbooks
```

## Quick start

1. Read [docs/00-lab-setup.md](docs/00-lab-setup.md) — launch your KodeKloud
   playground (3 VMs), note the IPs, and assign them to `node1`/`node2`/`node3`.
2. Copy `provisioning/common.sh` + the role-specific script(s) to each VM and
   run them. node1 gets two scripts: `node1-nginx.sh` then `node4-monitoring.sh`
   (monitoring is co-located there since KodeKloud caps out at 3 VMs).
3. `node4-monitoring.sh <node2-ip> <node3-ip>` templates `monitoring/*` with
   the other two VMs' IPs so Prometheus can scrape them.
4. Verify: open `http://<node1-ip>:3000` (Grafana), `http://<node1-ip>:9090`
   (Prometheus), `http://<node1-ip>/` (nginx → python app), and confirm the
   python app on node2 can reach Postgres on node3.
5. Work through [scenarios/](scenarios) 01 → 08 in order. For each one: break
   it deliberately, then investigate **before** looking at the runbook's
   answer section.
6. Deploy [chaos/chaos_monkey.py](chaos/chaos_monkey.py) on node2/node3 for
   the advanced challenge — it randomly injects CPU, memory, disk and
   connection-exhaustion failures so you have to troubleshoot without knowing
   in advance what broke.
7. Once you can answer a scenario without opening its runbook, try the
   [interview questions](docs/interview-questions.md) cold, then check your
   answers.

## Exit criteria

You can diagnose every scenario in `scenarios/` using only `top`, `ps`, `vmstat`,
`free`, `iostat`, `lsof`, `ss`, `tcpdump`, `strace`, `dmesg`, `journalctl` and
`systemctl` — without needing a tutorial.
