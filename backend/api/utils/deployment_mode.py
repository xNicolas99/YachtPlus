"""Deployment-mode detection and configuration health checks.

YachtPlus can run in two conceptually different modes:

  - LOCAL (default): public IP login is blocked, meant for LAN/homelab.
  - PUBLIC: public IP login is allowed, meant for VPS / reverse-proxy.

The mode is derived from the same env vars the rest of the app already
consumes; no new configuration surface is introduced. The checks here only
log warnings/errors at startup and expose a read-only status endpoint.
They never refuse to start — a misconfigured instance is still more useful
than one that silently fails to boot.
"""

from enum import Enum
from typing import List, Optional, Tuple
from pydantic import BaseModel


class DeploymentMode(str, Enum):
    LOCAL = "local"
    PUBLIC = "public"
    MIXED = "mixed"


class CheckSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ConfigCheck(BaseModel):
    rule_id: str
    severity: CheckSeverity
    message: str
    mode_expected: Optional[DeploymentMode] = None
    config_keys: List[str] = []


def detect_deployment_mode(settings) -> Tuple[DeploymentMode, List[ConfigCheck]]:
    """Derive a deployment mode and a list of config health checks.

    The function takes a Settings instance so it can reuse already-parsed
    values without re-implementing env parsing.
    """
    checks: List[ConfigCheck] = []

    block_public = settings.BLOCK_PUBLIC_IP_LOGIN
    # SECURE_COOKIES is tri-state: None (auto), True, False.
    explicit_secure = settings.SECURE_COOKIES is True
    auto_secure = settings.SECURE_COOKIES is None
    trusted = settings.TRUSTED_PROXIES or []
    allowed_hosts = settings.ALLOWED_HOSTS or []
    cors_origins = settings.CORS_ORIGINS or []
    environment = settings.ENVIRONMENT
    disable_auth = settings.DISABLE_AUTH
    allow_private = settings.ALLOW_PRIVATE_NETWORK_HOSTS

    # Detect whether any non-loopback proxy is trusted.
    loopback = {"127.0.0.1", "::1", "localhost", "[::1]"}
    has_nonloop_proxy = any(p not in loopback for p in trusted)
    hosts_star = "*" in allowed_hosts

    # ── S7-01: PUBLIC without secure cookies ──
    if not block_public and not explicit_secure:
        checks.append(
            ConfigCheck(
                rule_id="S7-01",
                severity=CheckSeverity.ERROR,
                message=(
                    "Public IP login is allowed but SECURE_COOKIES is not "
                    "explicitly enabled. Session cookies will be sent over "
                    "plain HTTP, enabling session hijacking."
                ),
                config_keys=["YACHT_BLOCK_PUBLIC_IP_LOGIN", "SECURE_COOKIES"],
            )
        )

    # ── S7-02: Host pinning disabled without external proxy trust ──
    if hosts_star and not has_nonloop_proxy:
        checks.append(
            ConfigCheck(
                rule_id="S7-02",
                severity=CheckSeverity.ERROR,
                message=(
                    "ALLOWED_HOSTS='*' disables Host-header pinning, but "
                    "TRUSTED_PROXIES only lists loopback addresses. Co-located "
                    "containers or LAN hosts may be able to spoof Host headers."
                ),
                config_keys=["YACHT_ALLOWED_HOSTS", "YACHT_TRUSTED_PROXIES"],
            )
        )

    # ── S7-03: PUBLIC with auto-detected secure cookies ──
    if not block_public and auto_secure:
        checks.append(
            ConfigCheck(
                rule_id="S7-03",
                severity=CheckSeverity.WARNING,
                message=(
                    "SECURE_COOKIES is set to auto-detect. Behind a reverse "
                    "proxy the scheme may be mis-detected if the proxy is not "
                    "in TRUSTED_PROXIES. Set SECURE_COOKIES=true explicitly "
                    "for public deployments."
                ),
                mode_expected=DeploymentMode.PUBLIC,
                config_keys=["SECURE_COOKIES", "YACHT_TRUSTED_PROXIES"],
            )
        )

    # ── S7-04: contradictory LOCAL + wildcard hosts ──
    if block_public and hosts_star:
        checks.append(
            ConfigCheck(
                rule_id="S7-04",
                severity=CheckSeverity.WARNING,
                message=(
                    "BLOCK_PUBLIC_IP_LOGIN blocks public IPs, but "
                    "ALLOWED_HOSTS='*' disables Host-header pinning. The "
                    "combination is contradictory and weaker than explicit "
                    "host pinning."
                ),
                config_keys=["YACHT_BLOCK_PUBLIC_IP_LOGIN", "YACHT_ALLOWED_HOSTS"],
            )
        )

    # ── S7-07: auth disabled + public login ──
    if disable_auth and not block_public:
        checks.append(
            ConfigCheck(
                rule_id="S7-07",
                severity=CheckSeverity.ERROR,
                message=(
                    "DISABLE_AUTH=true combined with public IP login means "
                    "anyone on the internet can control this instance "
                    "without credentials."
                ),
                config_keys=["DISABLE_AUTH", "YACHT_BLOCK_PUBLIC_IP_LOGIN"],
            )
        )

    # ── S7-08: legacy private-network hosts bypass active ──
    if allow_private and len(allowed_hosts) <= 1:
        checks.append(
            ConfigCheck(
                rule_id="S7-08",
                severity=CheckSeverity.WARNING,
                message=(
                    "ALLOW_PRIVATE_NETWORK_HOSTS=true bypasses Host-header "
                    "pinning for all RFC 1918 addresses, but ALLOWED_HOSTS is "
                    "very short. The bypass has little effect unless you "
                    "also list your internal hostnames."
                ),
                config_keys=["YACHT_ALLOW_PRIVATE_NETWORK_HOSTS", "YACHT_ALLOWED_HOSTS"],
            )
        )

    # ── S7-09: insecure cookies + wildcard CORS ──
    cors_has_wildcard = "*" in cors_origins
    http_origins = any(o.startswith("http://") for o in cors_origins)
    if not explicit_secure and (cors_has_wildcard or http_origins):
        checks.append(
            ConfigCheck(
                rule_id="S7-09",
                severity=CheckSeverity.ERROR,
                message=(
                    "CORS_ORIGINS contains a wildcard or http:// origins, but "
                    "SECURE_COOKIES is not True. Credentials may be sent to "
                    "untrusted origins."
                ),
                config_keys=["YACHT_CORS_ORIGINS", "SECURE_COOKIES"],
            )
        )

    # ── S7-10: positive feedback for a hardened local deployment ──
    if block_public and environment == "production" and explicit_secure:
        checks.append(
            ConfigCheck(
                rule_id="S7-10",
                severity=CheckSeverity.INFO,
                message=(
                    "Hardened local configuration detected: public IP login "
                    "blocked, production environment, secure cookies enabled."
                ),
                mode_expected=DeploymentMode.LOCAL,
                config_keys=["YACHT_BLOCK_PUBLIC_IP_LOGIN", "ENVIRONMENT", "SECURE_COOKIES"],
            )
        )

    # Determine mode
    if not block_public:
        if explicit_secure or has_nonloop_proxy:
            mode = DeploymentMode.PUBLIC
        else:
            mode = DeploymentMode.MIXED
    else:
        mode = DeploymentMode.LOCAL

    return mode, checks
