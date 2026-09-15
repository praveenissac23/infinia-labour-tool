"""Sending mail, for the few things that must reach somebody who is not
looking at the screen.

Nothing here is configured in code. The server is told by environment,
so no password lives in the repository:

    SMTP_HOST      smtp.example.com
    SMTP_PORT      587 (default)
    SMTP_USER      the mailbox that sends
    SMTP_PASSWORD  its password
    SMTP_FROM      what the message is from (defaults to SMTP_USER)
    SMTP_SSL       "1" for implicit SSL, otherwise STARTTLS is used

With no SMTP_HOST set, nothing is sent and nothing fails - the app
works exactly as before, and the attempt is noted in the log so it is
obvious that mail is not configured rather than silently missing.
"""
import os
import smtplib
import ssl
from email.message import EmailMessage


def configured() -> bool:
    return bool(os.environ.get("SMTP_HOST"))


def send(to: str, subject: str, body: str) -> tuple[bool, str]:
    """Returns (sent, reason). Never raises: a stock movement must not
    fail because a mail server is down."""
    host = os.environ.get("SMTP_HOST")
    if not host:
        return False, "no SMTP_HOST set - mail is not configured on this server"
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    sender = os.environ.get("SMTP_FROM") or user or "no-reply@infinia.ae"

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        if os.environ.get("SMTP_SSL") == "1":
            with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=15) as s:
                if user:
                    s.login(user, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=15) as s:
                s.starttls(context=ssl.create_default_context())
                if user:
                    s.login(user, password)
                s.send_message(msg)
        return True, "sent"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
