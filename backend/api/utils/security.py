import ipaddress
from fastapi import Request, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from api.db.models.settings import SMTPSettings
from api.db.models.users import LoginAttempt, User

def is_private_ip(ip: str) -> bool:
    if ip == '0.0.0.0':
        return True
    try:
        ip_obj = ipaddress.ip_address(ip)
        return ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_multicast
    except ValueError:
        return False # Invalid IP, treat as public/unsafe

def send_security_alert(db: Session, ip_address: str, reason: str, username: str = None):
    settings = db.query(SMTPSettings).first()
    if not settings:
        print("SMTP Settings not found, cannot send alert.")
        return

    admin_user = db.query(User).filter(User.username == settings.sender_email).first() # Fallback to sender email if admin email not stored explicitly
    # Better: Use the ADMIN_EMAIL from env or find superuser
    admin = db.query(User).filter(User.is_superuser == True).first()
    recipient = admin.username if admin else settings.sender_email

    subject = f"Security Alert: {reason}"
    body = f"""
    Security Alert for YachtPlus Server.

    Reason: {reason}
    IP Address: {ip_address}
    Username Attempted: {username or 'Unknown'}
    Timestamp: {datetime.utcnow()}

    This IP has been blocked or restricted.
    """

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = settings.sender_email
    msg['To'] = recipient

    try:
        if settings.use_tls:
            server = smtplib.SMTP(settings.server, settings.port)
            server.starttls()
        else:
            server = smtplib.SMTP(settings.server, settings.port)

        if settings.username and settings.password:
            server.login(settings.username, settings.password)

        server.sendmail(settings.sender_email, recipient, msg.as_string())
        server.quit()
    except Exception as e:
        print(f"Failed to send security alert: {e}")

def _resolve_client_ip(request: Request) -> str:
    """Return the originating client IP, trusting proxy headers only when the
    direct peer is on a private network."""
    client_ip = request.client.host
    if not client_ip or not is_private_ip(client_ip):
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


def _count_recent_failed_attempts(db: Session, client_ip: str, minutes: int = 15) -> int:
    time_threshold = datetime.utcnow() - timedelta(minutes=minutes)
    return (
        db.query(LoginAttempt)
        .filter(
            LoginAttempt.ip_address == client_ip,
            LoginAttempt.success == False,
            LoginAttempt.timestamp >= time_threshold,
        )
        .count()
    )


# Username-scoped counters: needed because the per-IP fail2ban above only
# stops a single attacker. A distributed attempt across many IPs targeting
# one username (credential stuffing, botnet brute force) would otherwise
# get unlimited tries per IP. We cap per-username attempts independently.
_USERNAME_LOCKOUT_WINDOW_MIN = 30
_USERNAME_LOCKOUT_THRESHOLD = 20


def _count_recent_failed_attempts_for_username(
    db: Session, username: str, minutes: int = _USERNAME_LOCKOUT_WINDOW_MIN,
) -> int:
    time_threshold = datetime.utcnow() - timedelta(minutes=minutes)
    return (
        db.query(LoginAttempt)
        .filter(
            LoginAttempt.username == username,
            LoginAttempt.success == False,
            LoginAttempt.timestamp >= time_threshold,
        )
        .count()
    )


def check_ip_restriction(request: Request, db: Session, username: str = None):
    client_ip = _resolve_client_ip(request)

    if not is_private_ip(client_ip):
        send_security_alert(db, client_ip, "Non-Private IP Login Attempt Blocked", username)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied from public IP.",
        )

    if _count_recent_failed_attempts(db, client_ip) >= 5:
        send_security_alert(db, client_ip, "Too many failed login attempts (Fail2Ban)", username)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="IP blocked due to too many failed login attempts.",
        )

    if username and _count_recent_failed_attempts_for_username(db, username) >= _USERNAME_LOCKOUT_THRESHOLD:
        send_security_alert(
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

def record_login_attempt(db: Session, ip_address: str, username: str, success: bool):
    attempt = LoginAttempt(ip_address=ip_address, username=username, success=success)
    db.add(attempt)
    db.commit()
