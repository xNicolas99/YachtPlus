# Fail2Ban Setup for YachtPlus

YachtPlus includes built-in rate limiting (5 attempts/minute), but for infrastructure-level blocking (iptables), you can use Fail2Ban.

## 1. Quick Setup (Host)

If you are running Fail2Ban on the host machine:

1. Copy `filter.d/yachtplus.conf` to `/etc/fail2ban/filter.d/yachtplus.conf`.
2. Append the content of `jail.local` to `/etc/fail2ban/jail.local`.
3. Adjust `logpath` in `jail.local` to point to your container logs or mounted log volume.
   - *Tip:* If using Docker, you might need to map the logs or use `journald` backend if logging driver is json-file.

## 2. Docker Sidecar

To run Fail2Ban as a container alongside YachtPlus, add this to your `docker-compose.yml`:

```yaml
services:
  fail2ban:
    image: crazymax/fail2ban:latest
    network_mode: "host"
    cap_add:
      - NET_ADMIN
      - NET_RAW
    volumes:
      - ./fail2ban/filter.d:/etc/fail2ban/filter.d:ro
      - ./fail2ban/jail.local:/etc/fail2ban/jail.d/yachtplus.local:ro
      - /var/log:/var/log:ro # Map where your logs are
      - /var/run/docker.sock:/var/run/docker.sock:ro
```

**Note:** The backend logs must be accessible to Fail2Ban. YachtPlus logs to stdout/stderr by default, which Docker captures. You may need to configure the `yachtplus` service to log to a file or use a logging driver that Fail2Ban can read.
