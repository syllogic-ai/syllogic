"""Provider-agnostic mail sending adapter.

Provider is chosen once from process environment variables, in this
precedence order: SMTP (if SMTP_HOST is set) > Resend (if RESEND_API_KEY
is set) > usesend (if USESEND_API_KEY is set). If none are configured,
get_mail_adapter() raises rather than silently no-op-ing.
"""
from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Protocol

import requests
import resend


class MailAdapter(Protocol):
    def send(self, to: list[str], subject: str, html: str, text: str) -> None:
        ...


class SmtpMailAdapter:
    def __init__(self, host: str, port: int, username: str, password: str, from_addr: str):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_addr = from_addr

    def send(self, to: list[str], subject: str, html: str, text: str) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.from_addr
        msg["To"] = ", ".join(to)
        msg.attach(MIMEText(text, "plain"))
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(self.host, self.port) as conn:
            conn.starttls()
            conn.login(self.username, self.password)
            conn.sendmail(self.from_addr, to, msg.as_string())


class ResendMailAdapter:
    def __init__(self, api_key: str, from_addr: str):
        self.from_addr = from_addr
        resend.api_key = api_key

    def send(self, to: list[str], subject: str, html: str, text: str) -> None:
        resend.Emails.send({
            "from": self.from_addr,
            "to": to,
            "subject": subject,
            "html": html,
            "text": text,
        })


class UsesendMailAdapter:
    def __init__(self, api_key: str, from_addr: str, base_url: str = "https://app.usesend.com/api"):
        self.api_key = api_key
        self.from_addr = from_addr
        self.base_url = base_url.rstrip("/")

    def send(self, to: list[str], subject: str, html: str, text: str) -> None:
        response = requests.post(
            f"{self.base_url}/v1/emails",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"from": self.from_addr, "to": to, "subject": subject, "html": html, "text": text},
            timeout=30,
        )
        response.raise_for_status()


def get_mail_adapter() -> MailAdapter:
    smtp_host = os.getenv("SMTP_HOST")
    if smtp_host:
        return SmtpMailAdapter(
            host=smtp_host,
            port=int(os.getenv("SMTP_PORT", "587")),
            username=os.getenv("SMTP_USERNAME", ""),
            password=os.getenv("SMTP_PASSWORD", ""),
            from_addr=os.getenv("SMTP_FROM", "reports@localhost"),
        )

    resend_key = os.getenv("RESEND_API_KEY")
    if resend_key:
        return ResendMailAdapter(api_key=resend_key, from_addr=os.getenv("RESEND_FROM", "reports@localhost"))

    usesend_key = os.getenv("USESEND_API_KEY")
    if usesend_key:
        return UsesendMailAdapter(
            api_key=usesend_key,
            from_addr=os.getenv("USESEND_FROM", "reports@localhost"),
            base_url=os.getenv("USESEND_BASE_URL", "https://app.usesend.com/api"),
        )

    raise RuntimeError(
        "No mail provider configured — set SMTP_HOST, or RESEND_API_KEY, or USESEND_API_KEY."
    )
