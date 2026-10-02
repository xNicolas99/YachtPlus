# Active fail2ban protection

Both Compose files automatically start this real fail2ban sidecar and require
its health check before launching YachtPlus. UID 1001; no network, Docker
socket or firewall capabilities.

- Jail `yachtplus`: five failures within 900 seconds; 3600-second ban.
- Input `/config/security/auth.log`, shared read-only into the guard. The log
  contains only UTC timestamp and canonical IP, never credentials/usernames.
- `action.d/yachtplus-state.conf` writes atomic persisted ban/expiry files.
- Output `/run/yachtplus-security`: guard writable, app read-only. IPv6 filenames
  replace colons with underscores; IPv4-mapped addresses normalize to IPv4.
- Supervisor validates real jail, action and active ban state before refreshing
  readiness. Missing/invalid/stale mandatory state fails closed in the app.
- nginx/backend enforce bans across UI, setup, authenticated API and terminal
  traffic. This action does not install host firewall rules or protect unrelated
  services. Existing HTTP streams are not cancelled retroactively.

```bash
docker compose exec -T fail2ban fail2ban-client -s /tmp/fail2ban.sock status yachtplus
docker compose exec -T fail2ban fail2ban-client -s /tmp/fail2ban.sock get yachtplus banip
docker compose logs fail2ban yachtplus
python3 scripts/security-stack-smoke.py --timeout 600
```

The image build executes the real filter with `fail2ban-regex`. The Linux stack
check performs real failed logins, ban/unban, persistence and protection outage
recovery. See [deployment and migration](../docs/SECURITY_DEPLOYMENT.md) for HTTP
proxy trust, recovery and the independent database login locks.
