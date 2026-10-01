# Scenario 6 — Network timeout

**Node:** node2 (app) talking to node3 (db) — inject the failure on node3 or the network path
**Learn:** `tcpdump`, `ss`, TCP retransmits/SYN backoff, `tc netem` latency injection

## Break it

Pick one, run **on node3** (the database):

```bash
# A) silently drop new connections from node2 (SYN packets vanish -- classic "hangs, doesn't fail fast")
sudo iptables -A INPUT -p tcp -s <node2-ip> --dport 5432 -j DROP

# B) add real latency/packet loss instead of a hard drop
sudo tc qdisc add dev eth0 root netem delay 400ms 100ms loss 15%

# C) simulate the service being overwhelmed: block new conns but let existing ones through
sudo iptables -A INPUT -p tcp -s <node2-ip> --dport 5432 -m state --state NEW -j DROP
```

## Investigate

On **node2** (the client):

```bash
time curl -v --max-time 5 "http://localhost:8000/db-check"   # or hit it through node1
ss -tn                                    # look for sockets stuck in SYN-SENT
ss -i                                      # retransmit counters (retrans, rto) on existing sockets
tcpdump -i any host <node3-ip> and port 5432 -n -c 20
```

On **node3** (the server), while node2 retries:

```bash
tcpdump -i any port 5432 -n -c 20         # do SYNs even arrive? do you see them but no SYN-ACK?
ss -tan state established '( dport = :5432 or sport = :5432 )'
iptables -L -n -v --line-numbers          # confirm the DROP rule is matching (packet counters increasing)
tc qdisc show dev eth0                    # confirm netem is active, if you used option B
```

## What you should find

- With option A: `ss -tn` on node2 shows the socket parked in `SYN-SENT`; `tcpdump` on node3
  shows SYNs arriving with **no SYN-ACK reply**; `iptables -L -n -v` shows the DROP rule's
  packet counter incrementing. The client eventually times out after retrying SYNs with
  exponential backoff (visible as repeated SYNs in `tcpdump` a few seconds apart).
- With option B: `curl` succeeds but is slow and sometimes fails; `ss -i` shows a nonzero
  `retrans` count and RTT estimates far above normal LAN latency.
- The key diagnostic distinction: **connection refused** (server up, port closed → immediate
  `RST`) vs **connection timeout** (packets dropped/filtered → client waits and retries) — a
  `tcpdump` capture is the fastest way to tell them apart, `ss`/`curl` timing alone can't.

## Fix / cleanup

```bash
# node3
sudo iptables -D INPUT -p tcp -s <node2-ip> --dport 5432 -j DROP
sudo iptables -D INPUT -p tcp -s <node2-ip> --dport 5432 -m state --state NEW -j DROP
sudo tc qdisc del dev eth0 root netem

curl "http://<node1-ip>/db-check"   # confirm recovery
```
