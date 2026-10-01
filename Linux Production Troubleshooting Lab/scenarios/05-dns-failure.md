# Scenario 5 — DNS failure

**Node:** node2 (app) — or any node
**Learn:** resolver order (`nsswitch.conf`), `resolv.conf`/`systemd-resolved`, DNS over the wire

## Break it

Pick one:

```bash
# A) point resolv.conf at a dead/wrong nameserver
cp /etc/resolv.conf /tmp/resolv.conf.bak
echo "nameserver 203.0.113.1" | sudo tee /etc/resolv.conf   # TEST-NET-3, guaranteed unreachable

# B) if systemd-resolved manages it, break the stub instead
sudo resolvectl dns eth0 203.0.113.1
sudo resolvectl domain eth0 ""

# C) corrupt /etc/nsswitch.conf resolver order
sudo sed -i 's/^hosts:.*/hosts: dns/' /etc/nsswitch.conf   # removes 'files', breaks /etc/hosts lookups too
```

## Investigate

```bash
cat /etc/resolv.conf
resolvectl status                      # if systemd-resolved is in use
getent hosts google.com                # uses the full NSS chain (files, dns, etc.)
dig google.com                         # bypasses NSS, talks straight to the configured resolver
dig @8.8.8.8 google.com                # does a *known-good* resolver work? isolates client vs network
nslookup google.com
tcpdump -i any port 53 -n &            # watch whether queries even leave the box
dig google.com; sleep 2; kill %1
journalctl -u systemd-resolved -n 50
```

## What you should find

- `dig google.com` times out or returns `SERVFAIL`/`connection timed out; no servers could be
  reached`, while `dig @8.8.8.8 google.com` succeeds — proving the *network* is fine, only your
  configured resolver is bad.
- `tcpdump port 53` shows outbound queries to `203.0.113.1` with no responses (or none at all,
  if the app never got that far), confirming where the chain breaks.
- If you broke `nsswitch.conf`, `getent hosts` for names in `/etc/hosts` (e.g. `localhost`)
  also starts failing even though DNS-only tools were never the cause — a good reminder to
  check `nsswitch.conf` before assuming "DNS" means "the DNS server".

## Fix / cleanup

```bash
sudo cp /tmp/resolv.conf.bak /etc/resolv.conf
sudo resolvectl revert eth0            # if you used systemd-resolved
sudo sed -i 's/^hosts:.*/hosts: files dns/' /etc/nsswitch.conf
sudo systemctl restart systemd-resolved 2>/dev/null || true
dig google.com    # confirm it's fixed
```
