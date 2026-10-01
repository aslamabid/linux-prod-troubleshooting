# Scenario 3 — Disk full (and deleted-but-open files)

**Node:** node3 (db) or node2 (app)
**Learn:** `df` vs `du` mismatches, inodes, how deleted-but-open files keep holding space

## Part A — plain disk full

### Break it

```bash
mkdir -p /tmp/chaos-monkey
fallocate -l 5G /tmp/chaos-monkey/bigfile.bin   # adjust size to whatever fills your disk
# or: sudo python3 chaos/chaos_monkey.py --once --action disk --duration 60
```

### Investigate

```bash
df -h                              # which filesystem is full?
du -sh /* 2>/dev/null | sort -rh | head -10          # biggest top-level dirs
find / -xdev -type f -size +100M 2>/dev/null -exec ls -lh {} \;   # biggest individual files
df -i                              # rule out inode exhaustion (lots of tiny files) too
```

### Fix

```bash
rm /tmp/chaos-monkey/bigfile.bin
df -h        # confirm space is back
```

## Part B — the "deleted but still full" trap

This is the classic gotcha: `rm` on a file that a process still has **open** does not free the
space until that process closes or is killed — but the file no longer shows up in `ls`/`find`,
so naive cleanup looks like it didn't work.

### Break it

```bash
# Start a process that keeps writing to (and holding open) a file, then delete the file
( tail -f /dev/null >> /tmp/chaos-monkey/held.log & echo $! > /tmp/chaos-monkey/held.pid )
# actually generate some content + hold the fd open:
python3 -c "
f = open('/tmp/chaos-monkey/held.log', 'w')
for _ in range(20):
    f.write('x' * 50_000_000)  # ~1GB total
    f.flush()
import time; time.sleep(3600)
" &
echo $! > /tmp/chaos-monkey/held.pid
rm /tmp/chaos-monkey/held.log     # deleted... but space is NOT freed
```

### Investigate

```bash
df -h /tmp                         # still shows the space as used
du -sh /tmp                        # but du (which walks the directory tree) shows it's gone from here!
lsof +L1                           # lists open files with link count 0 -- i.e. deleted-but-open
lsof | grep deleted
ls -li /proc/$(cat /tmp/chaos-monkey/held.pid)/fd/    # find the fd number pointing at the ghost file
```

## What you should find

- `df` reports space used that `du` can't account for → prime suspect is a deleted-but-open
  file. `lsof +L1` (or `lsof | grep deleted`) confirms it and shows the holding PID.
- The kernel only frees an inode's blocks when its link count **and** open-fd count both hit
  zero. `rm` drops the link count to 0 but the process's fd keeps it alive.

## Fix

```bash
PID=$(cat /tmp/chaos-monkey/held.pid)
# Option 1: kill the process holding it
kill $PID

# Option 2 (no restart needed): truncate via the /proc fd symlink -- frees space immediately
FD=$(ls -l /proc/$PID/fd | awk '/held.log/ || /deleted/ {print $9}' | head -1)
: > /proc/$PID/fd/$FD 2>/dev/null || kill $PID

df -h /tmp    # space reclaimed
```

In production this is exactly why log rotation tools default to `copytruncate` or
`postrotate` signals that make the app reopen its log file, instead of just `mv`+`rm`.
