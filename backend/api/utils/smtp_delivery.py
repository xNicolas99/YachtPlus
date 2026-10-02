"""Bounded SMTP delivery with certificate verification and at-rest credentials."""
import ssl
import smtplib
from api.utils.crypto import decrypt

def deliver(settings, recipient, message):
    context = ssl.create_default_context()
    server = None
    try:
        if settings.port == 465:
            server = smtplib.SMTP_SSL(settings.server, settings.port, timeout=10, context=context)
        else:
            server = smtplib.SMTP(settings.server, settings.port, timeout=10)
            if settings.use_tls:
                server.starttls(context=context)
        if settings.username and settings.password:
            server.login(settings.username, decrypt(settings.password))
        server.sendmail(settings.sender_email, recipient, message.as_string())
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                server.close()
