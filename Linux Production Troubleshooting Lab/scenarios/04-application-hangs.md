# Scenario 4 — Application hangs (and how that differs from uninterruptible sleep)

**Node:** node2 (app)
**Learn:** process states (`R`/`S`/`D`/`Z`/`T`), `strace`-ing a live process, blocking I/O

This scenario has two parts: a **hung application** (stuck in userspace/`S` state — e.g. a
deadlock or infinite wait) and a genuine **uninterruptible sleep (`D` state)** caused by slow
I/O, since they look similar in `ps` output but need different investigation and map directly
to interview question 4.

## Part A — application hang (deadlock-style)

### Break it

```bash
curl "http://<node1-ip>/hang" &     # the /hang endpoint sleeps forever, simulating a deadlock
```

### Investigate

```bash
ps -o pid,ppid,stat,wchan:32,cmd -C gunicorn
# STAT will show 'S' (interruptible sleep) -- it's blocked, but on something we can inspect

PID=<pid-from-above>
cat /proc/$PID/wchan; echo         # kernel function it's blocked in (e.g. hrtimer/futex)
strace -p $PID                     # attach and watch live syscalls (Ctrl-C to detach)
py-spy dump --pid $PID             # if py-spy is installed: full python stack trace, no restart needed
```

### What you should find

`strace -p` shows the process repeatedly in `nanosleep`/`clock_nanosleep` (matching the
`time.sleep(60)` loop in `app.py`'s `/hang` handler) — i.e. it's alive and interruptible, just
stuck in an intentional infinite loop. `py-spy dump` (if available) shows the exact Python
stack, which is the fastest way to diagnose a real hung Flask/Gunicorn worker in production
without restarting it.

### Fix

```bash
kill $PID          # SIGTERM; gunicorn's master respawns the worker
# or: systemctl restart python-app
```

## Part B — genuine uninterruptible sleep (`D` state)

A process in `D` state is blocked inside the kernel on I/O and **cannot be interrupted, even by
SIGKILL**, until the I/O completes or times out. We simulate this safely with a cgroup I/O
throttle instead of breaking real hardware.

### Break it

```bash
mkdir -p /tmp/chaos-monkey
# Throttle a scope to ~64KB/s write bandwidth on the root device, then force a big sync write
DEV=$(findmnt -no SOURCE / | sed 's/[0-9]*$//' )   # e.g. /dev/sda
MAJMIN=$(lsblk -no MAJ:MIN "$DEV" | head -1)
systemd-run --unit=chaos-io-throttle --scope \
  -p IOWriteBandwidthMax="$DEV 65536" \
  dd if=/dev/zero of=/tmp/chaos-monkey/slow.bin bs=1M count=200 conv=fsync
```

### Investigate

```bash
# While the dd above is running, in another shell:
ps -eo pid,stat,wchan:32,cmd | awk '$2 ~ /D/'   # find processes stuck in D state
cat /proc/<pid>/stack 2>/dev/null               # kernel stack (needs root); shows it's in an I/O wait path
iostat -x 1 5                                   # high %util / await on the throttled device
kill -9 <pid>                                   # notice: this does NOT remove it immediately while it's truly in D
```

### What you should find

- `ps`/`top` show `STAT=D` (or `D+`) for the `dd` process while it waits on the throttled write.
- `kill -9` is queued but **has no visible effect** until the kernel finishes the I/O the
  process is waiting on — this is the core answer to "why can't I kill a D-state process".
- `iostat -x` shows elevated `await`/`%util` on the device corresponding to the throttle.

### Cleanup

```bash
systemctl stop chaos-io-throttle   # removes the bandwidth cgroup limit
rm -f /tmp/chaos-monkey/slow.bin
```
