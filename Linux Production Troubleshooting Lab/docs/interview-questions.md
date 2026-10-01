# Interview questions — answer key

Try answering each from memory / hands-on experience first. Use this as a check, not a script
to memorize.

## 1. What happens when a Linux process runs out of memory?

- The process itself doesn't decide anything — the **kernel's OOM killer** steps in only once
  the system (or a cgroup, if memory limits are set) genuinely cannot satisfy an allocation
  even after reclaiming caches/swap.
- Before that point: allocations succeed due to **overcommit** (`vm.overcommit_memory`) — Linux
  hands out virtual address space optimistically, assuming not all of it will be touched.
  Memory pressure really bites when pages are actually written to (page faults demand real
  physical pages).
- Under pressure, the kernel first tries to reclaim: dropping clean page cache, writing back
  dirty pages, swapping out anonymous pages (if swap exists).
- If that's not enough, `out_of_memory()` runs, computing a **badness score** (`oom_score`) per
  process — roughly proportional to memory used, adjusted by `oom_score_adj`
  (`-1000` = never kill, `1000` = prime candidate) and a few heuristics (children, root
  processes get a small discount, etc.).
- The kernel `SIGKILL`s the highest-scoring process. This is unblockable/uncatchable — the
  process dies immediately without cleanup. `dmesg`/`journalctl -k` records the full candidate
  table and the kill event.
- If cgroup `memory.max` is set for a slice/service, the **cgroup-scoped** OOM killer fires
  first, killing something inside that cgroup only, protecting the rest of the system.

## 2. How do you investigate high CPU utilization?

1. **Confirm it's CPU, not something else masquerading as it**: `uptime` (load average vs
   `nproc`), `vmstat 1` (`us`/`sy`/`id`, and `r` = runnable queue length).
2. **Per-core view**: `mpstat -P ALL 1` — one hot core (single-threaded busy loop) vs all cores
   (parallel load) tells you a lot about the cause.
3. **Per-process view**: `top`/`htop`, or `pidstat -u 1` for short-lived spikes that `top`'s
   default 3s refresh might miss.
4. **Drill into the PID**: `ps -o pid,stat,wchan,cmd -p <pid>` (state), `strace -c -p <pid>`
   (syscall vs userspace-bound), `perf top -p <pid>` (where in the code, if `perf` is
   available), language-specific profilers (`py-spy`, `async-profiler`, etc.) for a stack
   trace without restarting the process.
5. Distinguish **user (`us`)** time (application code) from **system (`sy`)** time (heavy
   syscalls/context switches — often points at I/O, locking, or too many small syscalls) and
   from **steal (`st`)** time (a busy hypervisor neighbor, relevant on shared cloud VMs).

## 3. What happens when a process is killed with SIGKILL?

- `SIGKILL` (signal 9) cannot be caught, blocked, or ignored — it's handled entirely by the
  kernel, not delivered to the process's own signal handlers.
- The kernel immediately begins tearing the process down: it's marked for termination, removed
  from the scheduler's runnable state, and its resources are reclaimed — open file
  descriptors closed, memory unmapped, held locks released — without giving the process a
  chance to run any cleanup/`atexit`/`finally` code.
- The **exception**: a process stuck in **uninterruptible sleep (`D` state)** inside a kernel
  syscall (e.g. waiting on I/O) will *not* die until that syscall returns — the signal is
  queued but can't be delivered while the task isn't in an interruptible wait state. This is
  why `kill -9` on a `D`-state process can appear to "do nothing" for a while.
- Once torn down, the process becomes a **zombie (`Z`)** briefly until its parent `wait()`s on
  it and reaps the exit status; if the parent never reaps it, it stays a zombie (harmless but
  visible in `ps`) until the parent dies and `init`/PID 1 reaps it.
- Child processes are *not* automatically killed unless they were in the same process group and
  something sent the signal to the group, or a `PDEATHSIG` was set — orphaned children get
  reparented to PID 1 (or the nearest subreaper).

## 4. How do you investigate a process stuck in uninterruptible sleep (`D` state)?

- `D` state means the task is blocked inside a kernel syscall (almost always I/O: disk reads/
  writes, some NFS/network filesystem calls, certain driver operations) and, by design,
  **cannot be interrupted by signals** — not even `SIGKILL` — until the kernel operation
  completes, times out, or the underlying device error path returns control.
- Investigation steps:
  1. `ps -eo pid,stat,wchan:32,cmd | awk '$2 ~ /D/'` — find all `D`-state PIDs and their
     `wchan` (kernel function they're blocked in).
  2. `cat /proc/<pid>/stack` (root only) — kernel stack trace showing exactly where it's stuck.
  3. `iostat -x 1` / `iotop` — check `await`, `%util`, queue depth on the underlying block
     device; a persistently overloaded or failing disk is the most common root cause.
  4. Check `dmesg`/`journalctl -k` for I/O errors, SCSI timeouts, or (for NFS) "server not
     responding" messages.
  5. For network filesystems specifically, check mount options (`hard` vs `soft`,
     `intr`/`timeo`) — a `hard` mount with no `intr` will wait indefinitely for a dead server.
- You generally **cannot kill it**; you can only wait for the I/O to resolve, fix/replace the
  underlying storage or network path, or (for NFS) remount with different options. A reboot
  will also work but loses the same information a real fix needs.

## 5. How would you troubleshoot a server that is slow but has low CPU utilization?

Low CPU usually rules out compute-bound problems and points at contention/waiting instead:

1. **Check the run queue and iowait**: `vmstat 1` — a high `r` (runnable-but-waiting) column
   with low `us`/`sy` but high `wa` (iowait) points at disk; low everything with high load
   average can point at processes stuck in `D`.
2. **Disk I/O**: `iostat -x 1` — high `await`/`%util` means the disk is the bottleneck even
   though the CPU looks idle (the CPU is just waiting on I/O completion).
3. **Memory pressure without OOM**: `free -h`, `vmstat` `si`/`so` — heavy swapping thrashes
   the disk and stalls everything while CPU usage looks low because processes spend time
   blocked, not computing.
4. **Network**: `ss -i` for retransmits, `tcpdump` for unexpected latency/loss, DNS lookups
   silently adding seconds per request (see scenario 5).
5. **Lock contention / external dependency latency**: the app might be CPU-idle because it's
   blocked on a mutex, a slow downstream database query, or a rate-limited external API.
   `strace -p` or a language profiler (`py-spy dump`) showing the process parked in
   `futex`/`recvfrom`/`poll` is the tell.
6. **"Noisy neighbor" on shared infrastructure**: check `%steal` in `mpstat`/`top` — on a VM,
   high steal time means the hypervisor isn't giving you the CPU cycles you're entitled to,
   which looks like "slow but not really using CPU" from inside the guest.
7. Put it together: low CPU + slow response almost always means the bottleneck is **I/O,
   network, lock contention, or an external dependency** — chase whichever of `iostat`,
   `ss`/`tcpdump`, or `strace`/profiler output shows where time is actually being spent.
