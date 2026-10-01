# Scenario 1 — CPU reaches 100%

**Node:** node2 (app) — or any node, using `stress-ng`
**Learn:** process scheduling, load average, per-core vs per-process CPU, `/proc/<pid>` internals

## Break it

Option A — via the app:

```bash
curl "http://<node1-ip>/work?seconds=120"     # busy-loops one gunicorn worker for 120s
```

Option B — direct, node-agnostic:

```bash
stress-ng --cpu $(nproc) --timeout 120s
```

Option C — chaos monkey:

```bash
sudo python3 chaos/chaos_monkey.py --once --action cpu --duration 120
```

## Investigate (do this before reading further)

1. **Is the box actually CPU-bound?**
   ```bash
   uptime                 # load average vs `nproc` output
   nproc
   vmstat 1 5              # look at the `us`/`sy`/`id` columns and `r` (runnable queue)
   mpstat -P ALL 1 5       # per-core breakdown - one core pegged, or all of them?
   ```
2. **Which process?**
   ```bash
   top -o %CPU             # or: htop
   ps aux --sort=-%cpu | head -10
   pidstat -u 1 5          # per-process CPU over time, great for short spikes
   ```
3. **Drill into that PID:**
   ```bash
   ps -o pid,ppid,cmd,%cpu,stat -p <pid>
   cat /proc/<pid>/status | grep -E "State|Threads"
   cat /proc/<pid>/stat | awk '{print "utime="$14, "stime="$15}'
   strace -c -p <pid>      # sample syscalls for a few seconds then Ctrl-C - is it in userspace math or syscalls?
   ```
4. Confirm it correlates with what you broke (check `systemctl status python-app`, or the
   `stress-ng`/chaos-monkey PID from `ps --forest`).

## What you should find

- `uptime`'s load average rises toward (or past) `nproc`.
- `mpstat -P ALL` shows one or more cores at ~100% `%usr` (application busy-loop) — pure
  `stress-ng --cpu` typically shows 100% across all cores you gave it.
- `top`/`pidstat` point at a single PID (`gunicorn: worker` or `stress-ng-cpu`) burning CPU
  in `R` (running/runnable) state.
- `strace -c` on an app busy-loop shows almost **no** syscalls — it's spinning in userspace,
  which is why `strace -p` alone (without `-c` sampling) looks "stuck" with no output.

## Fix / cleanup

```bash
kill <pid>                       # or: systemctl restart python-app
pkill stress-ng                  # if you used option B
```

For real production hardening you'd cap this with a cgroup (`systemctl set-property
python-app.service CPUQuota=200%`) so one endpoint can't starve the whole node.
