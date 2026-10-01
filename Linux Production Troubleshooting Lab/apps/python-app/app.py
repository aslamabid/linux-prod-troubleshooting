"""
Lab app deployed on node2.

Deliberately includes endpoints that are easy to turn into troubleshooting
scenarios: CPU-bound work, memory growth, a blocking/hanging request, and a
DB round-trip to node3 (Postgres). None of this is "best practice" code --
it exists so you have knobs to break on purpose.
"""
import logging
import os
import time

from flask import Flask, jsonify, request

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("lab-app")

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_NAME = os.environ.get("DB_NAME", "labdb")
DB_USER = os.environ.get("DB_USER", "labuser")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "labpass")

# Deliberate: module-level list used by /leak to grow unbounded on purpose.
_leaked_memory = []


@app.get("/")
def index():
    return jsonify(status="ok", service="lab-app", pid=os.getpid())


@app.get("/health")
def health():
    return jsonify(status="healthy"), 200


@app.get("/work")
def work():
    """CPU-bound endpoint: busy-loops for `seconds` (default 5) on one core.

    Use this to reproduce scenario 1 (CPU reaches 100%).
    """
    seconds = float(request.args.get("seconds", 5))
    end = time.time() + seconds
    x = 0
    while time.time() < end:
        x += 1
    return jsonify(status="done", busy_seconds=seconds, iterations=x)


@app.get("/leak")
def leak():
    """Leaks ~`mb` megabytes of memory into a process-lifetime list.

    Use this to reproduce scenario 2 (memory exhausted / OOM killer).
    """
    mb = int(request.args.get("mb", 100))
    _leaked_memory.append(bytearray(mb * 1024 * 1024))
    total_mb = sum(len(chunk) for chunk in _leaked_memory) / (1024 * 1024)
    return jsonify(status="leaked", added_mb=mb, total_leaked_mb=total_mb)


@app.get("/hang")
def hang():
    """Blocks the worker thread/process indefinitely (simulated deadlock/hang).

    Use this to reproduce scenario 4 (application hangs). Investigate with
    `strace -p <pid>` and `py-spy dump --pid <pid>` (if installed).
    """
    log.info("Handling /hang: sleeping forever, pid=%s", os.getpid())
    while True:
        time.sleep(60)


@app.get("/db-check")
def db_check():
    """Round-trips to Postgres on node3 to prove app<->db connectivity."""
    import psycopg2

    try:
        conn = psycopg2.connect(
            host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
            connect_timeout=3,
        )
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
            cur.fetchone()
        conn.close()
        return jsonify(status="ok", db_host=DB_HOST)
    except Exception as exc:  # noqa: BLE001 - surfaced to caller on purpose
        log.exception("DB check failed")
        return jsonify(status="error", db_host=DB_HOST, error=str(exc)), 500


@app.get("/connect")
def connect_many():
    """Opens `count` sockets to node3:5432 and holds them (default 5s).

    Use this to reproduce scenario 8 (too many connections / exhausted fds).
    """
    import socket

    count = int(request.args.get("count", 50))
    hold_seconds = float(request.args.get("hold", 5))
    sockets = []
    opened = 0
    try:
        for _ in range(count):
            s = socket.create_connection((DB_HOST, 5432), timeout=2)
            sockets.append(s)
            opened += 1
    except Exception as exc:  # noqa: BLE001
        log.warning("Stopped opening sockets after %s: %s", opened, exc)
    time.sleep(hold_seconds)
    for s in sockets:
        s.close()
    return jsonify(status="done", requested=count, opened=opened)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
