import ipaddress
import logging
from fastapi import Request, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timezone, timedelta
import smtplib
from email.mime.text import MIMEText
import asyncio
from api.db.models.settings import SMTPSettings
from api.db.models.users import LoginAttempt, User
from api.settings import Settings

logger = logging.getLogger(__name__)
_settings = Settings()


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
        if settings_row.use_tls:
            server = smtplib.SMTP(settings_row.server, settings_row.port)
            server.starttls()
        else:
            server = smtplib.SMTP(settings_row.server, settings_row.port)

        if settings_row.username and settings_row.password:
            server.login(settings_row.username, settings_row.password)

        server.sendmail(settings_row.sender_email, recipient, msg.as_string())
        server.quit()
    except Exception as e:
        # Log the exception class but not its full text — smtplib errors can
        # embed the AUTH exchange, leaking credentials into container logs.
        logger.error("Failed to send security alert (%s)", type(e).__name__)


async def send_security_alert(db: AsyncSession, ip_address: str, reason: str, username: str = None):
    result = await db.execute(select(SMTPSettings).limit(1))
    settings = result.scalars().first()
    if not settings:
        logger.warning("SMTP settings not found, cannot send security alert.")
        return

    # Run the blocking SMTP send off the event loop.
    await asyncio.to_thread(_send_security_alert_sync, settings, ip_address, reason, username)


def _is_trusted_proxy(client_ip: str) -> bool:
    """Return True when client_ip matches a configured TRUSTED_PROXIES entry.

    Trusting "any private IP" (the previous behaviour) is unsafe in a Docker
    network: a sibling container is on a private subnet and would be able to
    spoof X-Real-IP / X-Forwarded-For. Require an explicit allowlist instead.
    """
    if not client_ip:
        return False
    try:
        peer = ipaddress.ip_address(client_ip)
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
    """Return the originating client IP.

    Only honour proxy headers when the direct peer is on the configured
    TRUSTED_PROXIES list. Otherwise use the direct peer — anyone can set
    X-Real-IP, so trusting it without an allowlist defeats the purpose of
    IP-based limits.

    request.client can be None in some ASGI/test setups; in that case we
    fall back to the loopback address so rate-limiting and IP-restriction
    checks don't crash, but we never trust proxy headers without a peer.
    """
    direct_peer = request.client.host if request.client else "127.0.0.1"
    client_ip = direct_peer
    if not _is_trusted_proxy(client_ip):
        return client_ip

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    forwarded_for = request.headers.get("X-Forwarded-For")
    if not forwarded_for:
        return client_ip

    # Walk X-Forwarded-For right-to-left, picking the first non-private hop.
    # Falls back to the rightmost entry when every hop is private.
    ips = [ip.strip() for ip in forwarded_for.split(",")]
    for ip in reversed(ips):
        if not is_private_ip(ip):
            return ip
    return ips[-1]


# Shared slowapi instance, created after key_func is defined so the
# forward reference resolves correctly. Routers import this from
# api.utils.security instead of creating their own Limiter objects so
# every endpoint uses the same in-memory state and key resolution.
from slowapi import Limiter
limiter = Limiter(
    key_func=rate_limit_key,
    default_limits=["100/minute"],
    headers_enabled=True,
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
    client_ip = _resolve_client_ip(request)

    # Hard-blocking every public IP made hosted/VPS deployments impossible
    # to log into; the block is now opt-out via YACHT_BLOCK_PUBLIC_IP_LOGIN.
    # getattr fallback keeps older Settings stubs (tests, embedders) working.
    if getattr(_settings, "BLOCK_PUBLIC_IP_LOGIN", True) and not is_private_ip(client_ip):
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
            detail="Account temporarily locked due to too many failed login attempts.",
        )

    return client_ip

async def record_login_attempt(db: AsyncSession, ip_address: str, username: str, success: bool):
    attempt = LoginAttempt(ip_address=ip_address, username=username, success=success)
    db.add(attempt)
    await db.commit()
