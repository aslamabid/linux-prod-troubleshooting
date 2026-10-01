#!/usr/bin/env python3
"""
Chaos monkey for the Linux Production Troubleshooting Lab (the "advanced
challenge"). Randomly injects one of four failure types so you have to
troubleshoot without knowing in advance what broke:

  cpu          - pegs N CPU cores to 100% for a while (stress-ng --cpu)
  memory       - allocates and holds a chunk of RAM (stress-ng --vm)
  disk         - fills free space in a target filesystem with a big file
  connections  - opens a burst of sockets to a target host:port and holds them

Every action logs what it did, when, and with which PID(s) to
/var/log/chaos-monkey.log (and stdout, so `journalctl -u chaos-monkey -f`
works when run as a systemd service) -- that log, plus `ps`/`top`/`lsof`/`df`,
is what you're meant to investigate with.

Safety valves (so a lab VM never gets permanently bricked):
  - disk fill never takes a filesystem above --max-disk-percent (default 90%)
  - memory hog never exceeds --max-mem-percent of total RAM (default 70%)
  - every action has a bounded duration and cleans up after itself
  - "connections" targets only host:port pairs given on the command line

Examples:
  sudo ./chaos_monkey.py --once                       # one random failure
  sudo ./chaos_monkey.py --once --action cpu           # force a specific one
  sudo ./chaos_monkey.py --loop --interval 300         # random failure every 5 min
  sudo ./chaos_monkey.py --once --action connections --target 10.0.0.5:5432
"""
from __future__ import annotations

import argparse
import logging
import os
import random
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

LOG_PATH = "/var/log/chaos-monkey.log"
DEFAULT_FILL_DIR = "/tmp/chaos-monkey"

log = logging.getLogger("chaos-monkey")


def setup_logging() -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    try:
        handlers.append(logging.FileHandler(LOG_PATH))
    except PermissionError:
        pass  # fall back to stdout-only if not root / no write access
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
    )


def require_root() -> None:
    if os.geteuid() != 0:
        log.error("This tool needs root (cgroup/fd limits, filling disk, etc). Re-run with sudo.")
        sys.exit(1)


def action_cpu(duration: int, workers: int | None) -> None:
    workers = workers or os.cpu_count() or 2
    log.warning("ACTION cpu: pegging %d worker(s) at 100%% for %ds", workers, duration)
    if shutil.which("stress-ng"):
        subprocess.run(
            ["stress-ng", "--cpu", str(workers), "--timeout", f"{duration}s"],
            check=False,
        )
    else:
        log.info("stress-ng not found, falling back to a python busy-loop")
        end = time.time() + duration
        while time.time() < end:
            pass
    log.info("ACTION cpu: finished")


def action_memory(duration: int, mb: int | None, max_mem_percent: int) -> None:
    total_kb = int(Path("/proc/meminfo").read_text().splitlines()[0].split()[1])
    total_mb = total_kb // 1024
    cap_mb = int(total_mb * max_mem_percent / 100)
    mb = min(mb or cap_mb, cap_mb)
    log.warning(
        "ACTION memory: allocating %dMB (cap=%dMB, %d%% of %dMB total) for %ds",
        mb, cap_mb, max_mem_percent, total_mb, duration,
    )
    if shutil.which("stress-ng"):
        subprocess.run(
            ["stress-ng", "--vm", "1", "--vm-bytes", f"{mb}M",
             "--vm-keep", "--timeout", f"{duration}s"],
            check=False,
        )
    else:
        log.info("stress-ng not found, falling back to python allocation")
        chunk = bytearray(mb * 1024 * 1024)
        time.sleep(duration)
        del chunk
    log.info("ACTION memory: finished, memory released")


def action_disk(duration: int, target_dir: str, max_disk_percent: int) -> None:
    target_dir_path = Path(target_dir)
    target_dir_path.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(target_dir_path)
    max_used = int(usage.total * max_disk_percent / 100)
    currently_used = usage.total - usage.free
    fill_bytes = max(max_used - currently_used, 0)
    fill_mb = fill_bytes // (1024 * 1024)

    fill_file = target_dir_path / f"chaos-fill-{int(time.time())}.bin"
    log.warning(
        "ACTION disk: filling %s with %dMB to reach ~%d%% used on %s for %ds",
        fill_file, fill_mb, max_disk_percent, target_dir, duration,
    )
    if fill_mb <= 0:
        log.info("ACTION disk: filesystem already at/above cap, skipping fill")
    else:
        subprocess.run(
            ["fallocate", "-l", f"{fill_mb}M", str(fill_file)],
            check=False,
        )
        log.info("df -h %s:\n%s", target_dir,
                  subprocess.run(["df", "-h", target_dir], capture_output=True, text=True).stdout)
        time.sleep(duration)

    if fill_file.exists():
        fill_file.unlink()
        log.info("ACTION disk: cleaned up %s", fill_file)
    log.info("ACTION disk: finished")


def action_connections(duration: int, target: str, count: int) -> None:
    host, _, port_str = target.rpartition(":")
    port = int(port_str)
    log.warning("ACTION connections: opening %d sockets to %s:%d for %ds", count, host, port, duration)
    sockets: list[socket.socket] = []
    opened = 0
    try:
        for _ in range(count):
            s = socket.create_connection((host, port), timeout=2)
            sockets.append(s)
            opened += 1
    except OSError as exc:
        log.info("Stopped after opening %d/%d sockets: %s", opened, count, exc)
    log.info("ACTION connections: %d sockets open, holding for %ds", opened, duration)
    time.sleep(duration)
    for s in sockets:
        s.close()
    log.info("ACTION connections: closed all sockets")


ACTIONS = ("cpu", "memory", "disk", "connections")


def run_once(args: argparse.Namespace) -> None:
    action = args.action or random.choice(ACTIONS)
    duration = args.duration or random.randint(20, 90)
    log.info("=== chaos-monkey firing action=%s duration=%ds ===", action, duration)

    if action == "cpu":
        action_cpu(duration, args.workers)
    elif action == "memory":
        action_memory(duration, args.mb, args.max_mem_percent)
    elif action == "disk":
        action_disk(duration, args.fill_dir, args.max_disk_percent)
    elif action == "connections":
        if not args.target:
            log.error("action=connections requires --target host:port, skipping")
            return
        action_connections(duration, args.target, args.count)
    else:
        log.error("Unknown action: %s", action)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--once", action="store_true", help="Run a single failure and exit")
    parser.add_argument("--loop", action="store_true", help="Run forever, firing a random failure every --interval seconds")
    parser.add_argument("--interval", type=int, default=300, help="Seconds between failures in --loop mode (default 300)")
    parser.add_argument("--action", choices=ACTIONS, help="Force a specific action instead of a random one")
    parser.add_argument("--duration", type=int, help="Seconds the failure lasts (default: random 20-90)")
    parser.add_argument("--workers", type=int, help="[cpu] number of cores to peg (default: all)")
    parser.add_argument("--mb", type=int, help="[memory] MB to allocate (default: up to --max-mem-percent)")
    parser.add_argument("--max-mem-percent", type=int, default=70, help="[memory] never exceed this %% of total RAM (default 70)")
    parser.add_argument("--fill-dir", default=DEFAULT_FILL_DIR, help="[disk] directory/filesystem to fill (default /tmp/chaos-monkey)")
    parser.add_argument("--max-disk-percent", type=int, default=90, help="[disk] never exceed this %% used on the target filesystem (default 90)")
    parser.add_argument("--target", help="[connections] host:port to connect to, e.g. 10.0.0.5:5432")
    parser.add_argument("--count", type=int, default=200, help="[connections] number of sockets to open (default 200)")
    args = parser.parse_args()

    setup_logging()
    require_root()

    if not args.once and not args.loop:
        parser.error("pass --once or --loop")

    if args.once:
        run_once(args)
        return

    log.info("chaos-monkey starting in loop mode, interval=%ds", args.interval)
    while True:
        run_once(args)
        log.info("Sleeping %ds before next failure...", args.interval)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
