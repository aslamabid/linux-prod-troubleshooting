# Scenario 7 — Service crashes

**Node:** node2 (app)
**Learn:** systemd unit states, restart limits, reading application + journal logs together

## Break it

Pick one:

```bash
# A) repeatedly SIGKILL it -- watch systemd's restart/backoff behavior
sudo systemctl restart python-app
for i in $(seq 1 6); do sudo pkill -9 -f gunicorn; sleep 1; done

# B) introduce a real startup failure (bad config) so it can't come back up
sudo sed -i 's/DB_HOST=.*/DB_HOST=this-host-does-not-exist/' /opt/lab/python-app/.env
sudo systemctl restart python-app

# C) corrupt the app itself
sudo sed -i '1i raise RuntimeError("boom")' /opt/lab/python-app/app.py
sudo systemctl restart python-app
```

## Investigate

```bash
systemctl status python-app                 # current state: active/failed/activating (auto-restart)
systemctl show python-app -p NRestarts,ActiveEnterTimestamp,ExecMainStatus,ExecMainCode
journalctl -u python-app -b                  # this boot's full log for the unit
journalctl -u python-app -p err -b           # only error-level+ lines
journalctl -u python-app --since "10 min ago" -f   # follow live while you retry
systemctl list-units --failed                # anything else failed as a side effect?
```

## What you should find

- Option A: `systemctl status` cycles through `activating (auto-restart)` → `active` as
  systemd honors `Restart=on-failure`/`RestartSec=2` from `python-app.service`. `NRestarts`
  increments each time. If you kill it faster than `StartLimitIntervalSec`/`StartLimitBurst`
  allow (defaults are lenient here since we didn't set them), it eventually lands in
  `failed (Result: start-limit-hit)` and **stops trying** — `systemctl reset-failed` is
  required before it will restart again.
- Option B: the unit reaches `active (running)` (gunicorn itself starts fine) but
  `journalctl -u python-app` shows repeated `psycopg2.OperationalError` tracebacks whenever
  `/db-check` is hit — a reminder that "the service is up" and "the service works" are
  different questions.
- Option C: `journalctl -u python-app -b` shows a Python traceback at import time and
  `ExecMainStatus`/`ExecMainCode` show a non-zero exit — systemd correctly reports this as a
  genuine crash loop, not a hang.

## Fix / cleanup

```bash
sudo git checkout -- /opt/lab/python-app/app.py 2>/dev/null   # or re-copy from apps/python-app/app.py
sudo sed -i "s/DB_HOST=.*/DB_HOST=<node3-ip>/" /opt/lab/python-app/.env
sudo systemctl reset-failed python-app
sudo systemctl restart python-app
systemctl status python-app
```
