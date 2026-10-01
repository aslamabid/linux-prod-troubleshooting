# Command cheatsheet

Grouped by what you're investigating. Not exhaustive — the goal is muscle memory for the
scenarios in this lab.

## Processes & CPU

```bash
top / htop
ps aux --sort=-%cpu | head
ps -o pid,ppid,stat,wchan:32,cmd -p <pid>
pidstat -u 1 5                 # per-process CPU over time
mpstat -P ALL 1 5              # per-core us/sy/id/steal
vmstat 1 5                     # r (run queue), us/sy/id/wa/st, si/so (swap)
uptime                         # load average
nproc
strace -c -p <pid>             # syscall summary (Ctrl-C to stop)
strace -p <pid>                # live syscall trace
perf top -p <pid>              # if perf is installed
py-spy dump --pid <pid>        # python stack trace, no restart needed
```

## Memory & OOM

```bash
free -h
vmstat 1
dmesg -T | grep -i -E "oom|killed process"
journalctl -k | grep -i oom
cat /proc/<pid>/status | grep -E "Vm|oom"
cat /proc/<pid>/oom_score
cat /proc/<pid>/oom_score_adj
systemctl set-property <unit> MemoryMax=512M     # cgroup memory cap
```

## Disk & filesystems

```bash
df -h                            # space per filesystem
df -i                            # inodes per filesystem
du -sh /* 2>/dev/null | sort -rh
find / -xdev -type f -size +100M 2>/dev/null
lsof +L1                         # open files with link count 0 (deleted but held open)
lsof | grep deleted
iostat -x 1 5                    # await, %util per device
iotop                            # per-process disk I/O
fallocate -l 1G file.bin         # quickly create a large file
```

## Networking

```bash
ip a / ip r
ss -tan                          # TCP sockets + state
ss -s                            # socket summary counts
ss -i                            # retransmits, RTT estimates for established sockets
tcpdump -i any port <port> -n
dig <name> / dig @8.8.8.8 <name>
resolvectl status
getent hosts <name>
iptables -L -n -v --line-numbers
tc qdisc show dev <iface>
curl -v --max-time 5 <url>
```

## systemd & logs

```bash
systemctl status <unit>
systemctl show <unit> -p NRestarts,ExecMainStatus,ExecMainCode
journalctl -u <unit> -b
journalctl -u <unit> -p err
journalctl -k                    # kernel ring buffer via journal
journalctl --since "10 min ago" -f
systemctl list-units --failed
systemctl reset-failed <unit>
```

## File descriptors & connections

```bash
lsof -p <pid> | wc -l
ls /proc/<pid>/fd | wc -l
cat /proc/<pid>/limits | grep "open files"
ulimit -n
ss -tan state established
```
