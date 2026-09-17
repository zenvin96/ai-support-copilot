"""Email 通知：stdlib smtplib，STARTTLS（587）或 SSL（465）。没配 SMTP_HOST / NOTIFY_EMAIL_TO 就不启用。"""
import asyncio
import smtplib
from email.message import EmailMessage
from email.utils import formatdate

from app.core.config import get_settings


def email_enabled() -> bool:
    s = get_settings()
    return bool(s.smtp_host and s.notify_email_to)


def build_message(subject: str, body: str, *, sender: str, to: list[str]) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(body)
    return msg


def _send_sync(msg: EmailMessage) -> None:
    s = get_settings()
    if s.smtp_port == 465:
        server = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=15)
    else:
        server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15)
    with server:
        if s.smtp_port != 465 and s.smtp_starttls:
            server.starttls()
        if s.smtp_user:
            server.login(s.smtp_user, s.smtp_password)
        server.send_message(msg)


async def send_email(subject: str, body: str) -> dict:
    s = get_settings()
    to = [x.strip() for x in s.notify_email_to.split(",") if x.strip()]
    msg = build_message(subject, body, sender=s.smtp_from or s.smtp_user, to=to)
    await asyncio.to_thread(_send_sync, msg)
    return {"to": to, "subject": subject}
