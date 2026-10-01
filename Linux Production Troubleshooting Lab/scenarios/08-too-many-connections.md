# Scenario 8 — Too many connections

**Node:** node2 (app) and/or node3 (db)
**Learn:** file descriptor limits, socket states, Postgres `max_connections`, `ulimit`

## Break it

```bash
# A) via the app: opens N sockets to node3:5432 and holds them
curl "http://<node1-ip>/connect?count=500&hold=60"

# B) direct, hammer Postgres past max_connections (default ~100)
for i in $(seq 1 150); do
  psql "host=<node3-ip> dbname=labdb user=labuser password=labpass" -c "select pg_sleep(60);" &
done

# C) chaos monkey
sudo python3 chaos/chaos_monkey.py --once --action connections --target <node3-ip>:5432 --count 500 --duration 60
```

## Investigate

On **node2** (or wherever you ran the client):

```bash
ss -s                                        # socket summary: total, TCP by state
ss -tan state established '( dport = :5432 )' | wc -l
lsof -p <pid> | wc -l                        # open fds for the offending process
cat /proc/<pid>/limits | grep "open files"   # soft/hard nofile limit for that process
ls /proc/<pid>/fd | wc -l                    # fd count directly from procfs
```

On **node3** (Postgres):

```bash
ss -tan '( sport = :5432 )' | wc -l
sudo -u postgres psql -c "select count(*) from pg_stat_activity;"
sudo -u postgres psql -c "show max_connections;"
journalctl -u postgresql -n 50 | grep -i "too many clients"
```

## What you should find

- Once concurrent connections approach the process's `nofile` limit (`ulimit -n`, default
  1024 for most shells but whatever `LimitNOFILE=` says for a systemd unit), new
  `socket()`/`accept()` calls start failing with `EMFILE`/`ENFILE` — visible as errors in the
  app log even though CPU/memory look fine.
- Once Postgres connections reach `max_connections`, new clients get
  `FATAL: sorry, too many clients already` — visible in `journalctl -u postgresql` and in
  `pg_stat_activity` maxing out.
- `ss -s` before vs after shows the `TCP` established count jump; `ss -tan state established`
  filtered by port pinpoints exactly which side (app or db) is accumulating sockets.

## Fix / cleanup

```bash
# Let held connections/sockets from options A-C time out and close on their own, or:
sudo pkill -f "connect\?count"     # nothing to kill client-side for curl, it already returned
sudo -u postgres psql -c "select pg_terminate_backend(pid) from pg_stat_activity where state = 'active' and pid <> pg_backend_pid();"

# Longer-term fixes to discuss/try:
# 1. Raise limits for the systemd unit: LimitNOFILE=65535 (already set in python-app.service)
# 2. Add connection pooling in front of Postgres (pgbouncer) instead of 1:1 app<->db connections
# 3. Set sane socket/connection timeouts in the app so it fails fast instead of piling up
```
