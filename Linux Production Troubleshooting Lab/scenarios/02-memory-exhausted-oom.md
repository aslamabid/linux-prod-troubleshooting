# Scenario 2 — Memory exhausted / OOM killer

**Node:** node2 (app)
**Learn:** virtual vs resident memory, overcommit, the OOM killer's scoring, `oom_score_adj`

## Break it

```bash
# Repeat until memory pressure builds (each call leaks ~500MB permanently in the process)
for i in 1 2 3 4 5 6 7 8; do curl "http://<node1-ip>/leak?mb=500"; sleep 1; done
```

Or direct:

```bash
stress-ng --vm 1 --vm-bytes 90% --vm-keep --timeout 60s
```

Or chaos monkey:

```bash
sudo python3 chaos/chaos_monkey.py --once --action memory --duration 60
```

## Investigate

1. **Watch memory fill up:**
   ```bash
   free -h
   vmstat 1 5          # `free`, `buff/cache`, and `si`/`so` (swap in/out) columns
   watch -n1 'free -h; echo; ps aux --sort=-%mem | head -6'
   ```
2. **Did the OOM killer fire?**
   ```bash
   dmesg -T | grep -i -E "oom|killed process"
   journalctl -k | grep -i -E "oom|out of memory"
   grep -i oom /var/log/syslog 2>/dev/null
   ```
3. **Who got killed, and why that process?**
   ```bash
   dmesg -T | grep -A1 -B20 "Out of memory"   # shows the candidate table with oom_score per process
   cat /proc/<pid>/oom_score                   # higher = more likely to be killed
   cat /proc/<pid>/oom_score_adj               # -1000 = never kill, 1000 = kill first
   ```
4. **Confirm the service actually died:**
   ```bash
   systemctl status python-app     # look for "signal=KILL" and a restart
   journalctl -u python-app -n 50
   ```

## What you should find

- `free -h` shows `available` dropping toward 0 while your leak endpoint runs.
- `dmesg` shows a block like `Out of memory: Killed process <pid> (gunicorn) total-vm:...,
  anon-rss:...`, followed by the kernel's per-process candidate table with `oom_score` values.
- The kernel picks the process with the highest `oom_score` — normally proportional to the
  % of memory it's using, adjusted by `oom_score_adj`. It is **not** necessarily the process
  that most recently allocated memory.
- `systemctl status` shows the unit was killed by `SIGKILL` and restarted (`Restart=on-failure`
  in `python-app.service`).

## Fix / cleanup

The leaked memory disappears with the process (systemd auto-restarts it). To prevent a single
endpoint from taking down the whole node in the future:

```bash
# Cap the service's memory so the cgroup OOM killer targets only this unit, not the whole box
systemctl set-property python-app.service MemoryMax=512M MemoryHigh=400M
systemctl restart python-app
```

Re-run the leak test — this time `dmesg` should show a **cgroup-scoped** OOM kill instead of
a system-wide one, and other processes on the node stay unaffected.
