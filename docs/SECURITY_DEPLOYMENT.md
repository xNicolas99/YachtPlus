# Protected deployment and migration

Both Compose files start YachtPlus, its isolated Docker socket proxy and real
fail2ban. Default LAN access covers UI, initial setup, authenticated API and
terminal. Public access requires confirmation by an active local administrator
in Server Settings → Security, with mandatory, healthy fail2ban.

## Start and verify

```bash
docker compose up -d --build
docker compose ps
docker compose exec -T yachtplus id
docker compose exec -T fail2ban id
docker compose exec -T fail2ban fail2ban-client -s /tmp/fail2ban.sock status yachtplus
python3 scripts/security-stack-smoke.py --timeout 600
```

Expected UIDs are 1000 and 1001. Compose waits for a healthy jail. The app and
guard drop all capabilities; their root filesystems are read-only. The guard
has no network, host socket or firewall privilege. The daemon/socket proxy
remain powerful infrastructure; this stack does not make Docker rootless.

The Docker socket proxy also keeps its root filesystem read-only. Its bounded
`/run` tmpfs is required for HAProxy's `/run/haproxy.pid`; `/tmp` alone is
insufficient. Keep both tmpfs entries when adapting either Compose file.

The Linux stack test uses a unique project/fresh volumes and checks real failed
logins, bans, unbans, persistence, proxy attribution, protection outage/recovery,
runtime privileges and loopback backend. It cleans only its test resources.
Absent Docker fails the gate. This is a required publication CI job.
Startup failures report container health and app-visible state UID/GID/modes;
diagnostics never dump container environment variables or secret values.
The release image also requires fail2ban by default when started without Compose;
without the guard/state mounts it rejects access. Direct source development has
an optional guard. Publication tests the exact candidate image in the protected
stack before pushing it; its separate isolated startup check explicitly disables
the guard requirement only for that check.

## Addresses and HTTP proxies

Local sources are RFC1918 IPv4, loopback and IPv6 ULA. Link-local, unspecified,
multicast and reserved addresses are excluded. Destination hostname validation
is separate; set `YACHT_ALLOWED_HOSTS` for DNS names. Private destination IP
literals work in Compose by default.

For an external HTTPS proxy, configure its exact transport IP/CIDR in `.env`:

```dotenv
YACHT_ALLOWED_HOSTS=yacht.example.org,localhost,127.0.0.1,[::1]
YACHT_HTTP_TRUSTED_PROXIES=172.20.0.2/32
```

Recreate YachtPlus after changing trust. nginx validates the XFF chain and
overwrites client headers; forwarded HTTPS is accepted only from trusted peers.
Keep backend `YACHT_TRUSTED_PROXIES=127.0.0.1,::1`. Do not trust every LAN client,
private subnet or `0.0.0.0/0`. An upstream proxy must preserve the real client
address; otherwise per-client access/bans cannot identify Internet sources.
Use HTTPS for public access. VPS administrators can initially connect over a
private VPN or SSH tunnel, then opt in locally. The historical
`YACHT_BLOCK_PUBLIC_IP_LOGIN=false` flag no longer opens access.

## Active protection and recovery

Five failed logins in 900 seconds create a 3600-second ban. The guard reads the
deterministic `/config/security/auth.log` without usernames/credentials, and
writes persisted bans and heartbeat into `/run/yachtplus-security`; the app
mounts that state read-only. Bans apply to all new HTTP requests and terminal
frames, including existing terminal sessions. Established HTTP streams are
not retroactively cancelled. This is an application fail2ban action; it does
not install host iptables rules or protect unrelated services/TCP traffic.

The state root and `bans` directory must be traversable by the app UID 1000:
the guard owns them as UID 1001, directories use `0755`, and published JSON
files use `0644`. The app's state mount remains read-only. Fail2ban 1.0.2
starts actions with `umask 077`, so `mkdir(mode=0755)` by itself creates a
`0700` directory. The action explicitly reapplies `0755` on every start,
including existing state volumes; readiness under the guard UID alone does
not establish that the app can read those files.

Readiness checks actual jail, action and enforced bans about every 5 seconds.
Missing, invalid or older than 30 second state fails closed: backend 503, nginx
500 for an unexpected auth subrequest failure. The UI cannot load during that
outage. Repair the guard instead of disabling required protection.

```bash
docker compose logs fail2ban yachtplus
docker compose exec -T fail2ban fail2ban-client -s /tmp/fail2ban.sock get yachtplus banip
docker compose exec -T fail2ban stat -c '%a %u:%g %n' /run/yachtplus-security /run/yachtplus-security/bans
docker compose exec -T yachtplus python -c "from pathlib import Path; p = Path('/run/yachtplus-security'); print((p / 'ready.json').read_text()); print([item.name for item in (p / 'bans').iterdir()])"
# After investigating the failures, recover a known administrator IP:
docker compose exec -T fail2ban fail2ban-client -s /tmp/fail2ban.sock set yachtplus unbanip 192.168.1.50
```

Database login locks remain independent: an external unban does not clear the
15-minute IP or 30-minute account failure window. Keep space for persistent
database/security logs; mandatory log-write failures reject the login. Guard
state and database survive restarts.

If fail2ban is healthy but the app still returns protection-unavailable 503,
check directory traversal and JSON readability from inside the app. Rebuild
and recreate the corrected guard; its start action repairs the ban-directory
mode without deleting persisted bans. If the proxy log reports a read-only
`/run/haproxy.pid`, restore its `/run` tmpfs and recreate the proxy. Check
`docker compose logs dockerproxy` as well as the guard/app logs. Do not
disable protection, remove read-only mounts or make state world-writable to
work around either startup failure.

## Workloads and updates

New form deployments use nonzero numeric UID/GID 1000:1000, read-only rootfs,
cap_drop ALL, no new privileges, 256 processes and bounded writable `/tmp`/`/run`.
Select a suitable numeric user and writable data volumes owned by it. Host
networking/device passthrough require an explicit active-administrator Image
compatibility acknowledgement. Compatibility uses image user (possibly root),
writable rootfs/default capabilities, but retains no new privileges/process
limit. An incompatible image never triggers an automatic downgrade.

Saving Compose requires an active administrator and injects visible restricted
defaults. Per-service `x-yachtplus-security: image-default` is the expert
exception. Restricted services reject dangerous namespaces/capabilities,
devices, sensitive or traversing binds and custom volume drivers/options.
Includes must be inlined. YAML is normalized; comments may be reformatted or
removed. Existing external YAML/running workloads are not silently rewritten.

Updates use disposable UID 1000 workers from the current Yacht image, attached
only to `YACHT_DOCKER_PROXY_NETWORK`, without host socket mounts or external
Watchtower. Volumes/security settings/original image reference persist.
Originals remain until replacement startup/health passes; failures attempt
rollback. Without an image healthcheck only startup can be checked. Retained
backups/workers stay visible for inspection after cleanup errors; a later
update can replace a verified completed worker.

Form edits also retain the original and volumes until startup/health succeeds,
with rollback on failures and a process-shared edit lock. Lost Docker responses
allow cleanup only with a matching transaction label. The normal workload editor
rejects YachtPlus, its Docker proxy and fail2ban. The dedicated update worker can
replace YachtPlus itself; update proxy and guard through their Compose deployment.

## Upgrade from the previous deployment

These access/configuration changes are breaking. Version 3.0.0 remains a
verification candidate until Linux image/stack, visual and staging migration
checks pass.

The 3.0.2 patch addresses the CI-confirmed state-directory and proxy-PID
startup failures. Rebuild/recreate the guard and proxy with both corrected
Compose contracts when upgrading. Its successful Linux protection-stack
verification remains required; earlier local test results do not establish it.

1. Stop the old app and back up config/Compose data, preserving database,
   signing key, Fernet salt and setup flag.
2. Adopt the protected Compose stack while retaining the actual old config
   volume/bind. Never use `down -v` on production.
3. Existing config/Compose/log mounts must be writable by 1000:1000. An
   administrator may need to repair ownership once on verified host paths.
   The app never runs root or repairs ownership; do not make data world-writable.
4. Add persistent logs and guard-state volumes with the Compose mount directions.
   Fresh volumes receive ownership from the images. Never mount state writable
   into the app. The state root/bans must be traversable by UID 1000; the
   corrected guard action restores its own bans directory to `0755` on start.
   Retain the Docker proxy's bounded `/run` tmpfs for its PID file.
5. Configure exact HTTP proxy trust/hostname, start, verify the real jail and
   log in locally. Public access now requires the confirmed UI setting.
6. Audit existing workloads before recreating them. Legacy form edits require
   fresh compatibility acknowledgement; saved Compose gains restricted defaults.
   Test writable data, retained database, health and rollback on a staging host.
