FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends fail2ban python3 && \
    rm -rf /var/lib/apt/lists/* && \
    rm -f /etc/fail2ban/jail.d/defaults-debian.conf && \
    groupadd -g 1000 yachtlogs && useradd -u 1001 -g yachtlogs -M -s /usr/sbin/nologin yachtguard && \
    mkdir -p /run/yachtplus-security /config/security /opt/yachtplus && \
    touch /config/security/auth.log && \
    chown 1001:1000 /run/yachtplus-security && chmod 755 /run/yachtplus-security && \
    chown -R 1000:1000 /config/security && chmod 750 /config/security && chmod 640 /config/security/auth.log
COPY fail2ban.local jail.local /etc/fail2ban/
COPY filter.d/yachtplus.conf /etc/fail2ban/filter.d/yachtplus.conf
COPY action.d/yachtplus-state.conf /etc/fail2ban/action.d/yachtplus-state.conf
COPY state_action.py supervise.py /opt/yachtplus/
USER 1001:1000
RUN fail2ban-regex '2026-09-30 12:00:00 yachtplus-auth failure ip=192.168.1.10' \
    /etc/fail2ban/filter.d/yachtplus.conf | grep -q '1 matched'
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
    CMD python3 /opt/yachtplus/supervise.py --healthcheck
CMD ["python3", "/opt/yachtplus/supervise.py"]
