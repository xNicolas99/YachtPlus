import ipaddress
import logging
import os
import stat
from pathlib import Path
from fastapi import Request, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timezone, timedelta
import smtplib
from email.mime.text import MIMEText
import asyncio
import time
from api.utils.smtp_delivery import deliver
from api.db.models.settings import SMTPSettings
from api.db.models.users import LoginAttempt, User
from api.settings import get_settings
from api.utils.access_policy import canonical_ip, is_local_client, is_usable_client, read_access_policy, ProtectionUnavailable

# using module-level _settings
_settings = get_settings()

logger = logging.getLogger(__name__)


def is_private_ip(ip: str) -> bool:
    # The literal here is the unspecified-address sentinel, NOT a bind
    # target — we treat it as private/unsafe so the SSRF guard refuses
    # to connect to it. Suppress Bandit's B104 "binding to all interfaces"
    # match — this is the opposite intent.
    if ip == '0.0.0.0':  # nosec B104
        return True
    try:
        ip_obj = ipaddress.ip_address(ip)
        return ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_multicast
    except ValueError:
        return False # Invalid IP, treat as public/unsafe


def _send_security_alert_sync(settings_row, ip_address: str, reason: str, username: str = None):
    """Synchronous SMTP send, run in a thread to avoid blocking the loop."""
    recipient = settings_row.sender_email
    subject = f"Security Alert: {reason}"
    body = f"""
    Security Alert for YachtPlus Server.

    Reason: {reason}
    IP Address: {ip_address}
    Username Attempted: {username or 'Unknown'}
    Timestamp: {datetime.now(timezone.utc)}

    This IP has been blocked or restricted.
    """

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = settings_row.sender_email
    msg['To'] = recipient

    try:
        deliver(settings_row, recipient, msg)
    except Exception as e:
        # Log the exception class but not its full text — smtplib errors can
        # embed the AUTH exchange, leaking credentials into container logs.
        logger.error("Failed to send security alert (%s)", type(e).__name__)


_alert_tasks = set()
_last_alert = 0.0

async def send_security_alert(db: AsyncSession, ip_address: str, reason: str, username: str = None):
    global _last_alert
    if _alert_tasks or time.monotonic() - _last_alert < 30:
        return
    result = await db.execute(select(SMTPSettings).limit(1))
    settings = result.scalars().first()
    if not settings:
        logger.warning("SMTP settings not found, cannot send security alert.")
        return

    # Run the blocking SMTP send off the event loop.
    _last_alert = time.monotonic()
    task = asyncio.create_task(asyncio.to_thread(_send_security_alert_sync, settings, ip_address, reason, username))
    _alert_tasks.add(task)
    task.add_done_callback(_alert_tasks.discard)


def _is_trusted_proxy(client_ip: str) -> bool:
    """Return True when client_ip matches a configured TRUSTED_PROXIES entry.

    Trusting "any private IP" (the previous behaviour) is unsafe in a Docker
    network: a sibling container is on a private subnet and would be able to
    spoof X-Real-IP / X-Forwarded-For. Require an explicit allowlist instead.
    """
    if not client_ip:
        return False
    try:
        canonical = canonical_ip(client_ip)
        if canonical is None:
            return False
        peer = ipaddress.ip_address(canonical)
    except ValueError:
        return False

    for entry in getattr(_settings, "TRUSTED_PROXIES", []) or []:
        try:
            if "/" in entry:
                if peer in ipaddress.ip_network(entry, strict=False):
                    return True
            else:
                if peer == ipaddress.ip_address(entry):
                    return True
        except ValueError:
            logger.warning("Skipping invalid TRUSTED_PROXIES entry")
    return False


def rate_limit_key(request: Request) -> str:
    """slowapi `key_func` that respects TRUSTED_PROXIES.

    Previously every limiter used slowapi.util.get_remote_address, which
    returns `request.client.host` and therefore reported 127.0.0.1 for
    every request — because YachtPlus's own nginx sits in front of
    gunicorn on the loopback. That made the rate limit globally shared:
    one bad actor could blow the budget for every other user. Routing
    through _resolve_client_ip honours X-Real-IP / X-Forwarded-For ONLY
    when the direct peer is in TRUSTED_PROXIES, so a sibling container
    can't spoof the header to dodge the limit either.
    """
    return _resolve_client_ip(request)


def _resolve_client_ip(request: Request) -> str:
    """Resolve validated addresses through explicitly trusted proxy hops only.

    Unknown peers remain unknown, never localhost. X-Real-IP is a single
    normalized value supplied by nginx after its trusted real-IP processing.
    XFF stops at the first untrusted hop, even when that hop is a LAN address.
    """
    direct_peer = canonical_ip(request.client.host) if request.client else None
    if direct_peer is None:
        return "unknown"
    if not _is_trusted_proxy(direct_peer):
        return direct_peer
    real_ip = request.headers.get("X-Real-IP")
    if real_ip is not None:
        return canonical_ip(real_ip) or "unknown"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if not forwarded_for:
        return direct_peer
    if len(forwarded_for) > 8192:
        return "unknown"
    ips = [canonical_ip(value) for value in forwarded_for.split(",")]
    if not ips or any(value is None for value in ips):
        return "unknown"
    current = direct_peer
    for candidate in reversed(ips):
        if not _is_trusted_proxy(current):
            break
        current = candidate
    return current


# Shared slowapi instance, created after key_func is defined so the
# forward reference resolves correctly. Routers import this from
# api.utils.security instead of creating their own Limiter objects so
# every endpoint uses the same in-memory state and key resolution.
from slowapi import Limiter
limiter = Limiter(
    key_func=rate_limit_key,
    default_limits=["100/minute"],
    headers_enabled=True,
    storage_uri=_settings.RATE_LIMIT_STORAGE_URI,
)


async def _count_recent_failed_attempts(db: AsyncSession, client_ip: str, minutes: int = 15) -> int:
    time_threshold = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    result = await db.execute(
        select(func.count())
        .select_from(LoginAttempt)
        .filter(
            LoginAttempt.ip_address == client_ip,
            LoginAttempt.success == False,
            LoginAttempt.timestamp >= time_threshold,
        )
    )
    return result.scalar()


# Username-scoped counters: needed because the per-IP fail2ban above only
# stops a single attacker. A distributed attempt across many IPs targeting
# one username (credential stuffing, botnet brute force) would otherwise
# get unlimited tries per IP. We cap per-username attempts independently.
_USERNAME_LOCKOUT_WINDOW_MIN = 30
_USERNAME_LOCKOUT_THRESHOLD = 20


async def _count_recent_failed_attempts_for_username(
    db: AsyncSession, username: str, minutes: int = _USERNAME_LOCKOUT_WINDOW_MIN,
) -> int:
    time_threshold = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    result = await db.execute(
        select(func.count())
        .select_from(LoginAttempt)
        .filter(
            LoginAttempt.username == username,
            LoginAttempt.success == False,
            LoginAttempt.timestamp >= time_threshold,
        )
    )
    return result.scalar()


async def check_ip_restriction(request: Request, db: AsyncSession, username: str = None):
    from api.db.crud.users import normalize_username
    username = normalize_username(username) if username else None
    client_ip = _resolve_client_ip(request)
    if not is_usable_client(client_ip):
        raise HTTPException(status_code=403, detail="Invalid client address")

    try:
        allow_public = read_access_policy(_settings)["allow_public"]
    except ProtectionUnavailable:
        raise HTTPException(status_code=503, detail="Security protection unavailable") from None
    if not allow_public and not is_local_client(client_ip):
        await send_security_alert(db, client_ip, "Non-Private IP Login Attempt Blocked", username)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied from public IP.",
        )

    if await _count_recent_failed_attempts(db, client_ip) >= 5:
        await send_security_alert(db, client_ip, "Too many failed login attempts (Fail2Ban)", username)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="IP blocked due to too many failed login attempts.",
        )

    if username and await _count_recent_failed_attempts_for_username(db, username) >= _USERNAME_LOCKOUT_THRESHOLD:
        await send_security_alert(
            db,
            client_ip,
            f"Account locked: {_USERNAME_LOCKOUT_THRESHOLD} failed logins for username in "
            f"{_USERNAME_LOCKOUT_WINDOW_MIN} min (possible distributed brute force)",
            username,
        )
        # Same response wording as the IP block path so a probing attacker
        # can't differentiate "this username is being attacked" from
        # "my IP got banned" through error inspection.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="IP blocked due to too many failed login attempts.",
        )

    return client_ip

async def record_login_attempt(db: AsyncSession, ip_address: str, username: str, success: bool):
    from api.db.crud.users import normalize_username
    username = normalize_username(username)
    attempt = LoginAttempt(ip_address=ip_address, username=username, success=success)
    db.add(attempt)
    await db.commit()
    from api.utils.audit import log_activity
    await log_activity(db, username, "login.success" if success else "login.failure", ip_address)
    if not success:
        try:
            await asyncio.to_thread(_append_auth_failure, ip_address)
        except (OSError, ValueError):
            logger.error("Could not record fail2ban authentication event")
            if getattr(_settings, "FAIL2BAN_REQUIRED", False):
                raise HTTPException(status_code=503, detail="Security protection unavailable") from None


def _append_auth_failure(client_ip):
    canonical = canonical_ip(client_ip)
    if canonical is None:
        raise ValueError("Cannot log an invalid client IP")
    destination = Path(getattr(_settings, "SECURITY_LOG", "/config/security/auth.log"))
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    line = f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} yachtplus-auth failure ip={canonical}\n".encode("ascii")
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(destination, flags, 0o640)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("Authentication log must be a regular file")
        # One append operation prevents interleaved records across workers.
        if os.write(fd, line) != len(line):
            raise OSError("Incomplete security log write")
        os.fsync(fd)
    finally:
        os.close(fd)
