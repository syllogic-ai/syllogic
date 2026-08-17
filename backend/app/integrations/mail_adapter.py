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
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        from_addr: str,
        timeout: float = 30,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_addr = from_addr
        self.timeout = timeout

    def send(self, to: list[str], subject: str, html: str, text: str) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.from_addr
        msg["To"] = ", ".join(to)
        msg.attach(MIMEText(text, "plain"))
        msg.attach(MIMEText(html, "html"))

        # Port 465 is implicit TLS (SMTPS) — connecting with plain SMTP +
        # starttls() on that port hangs/fails against most providers.
        smtp_cls = smtplib.SMTP_SSL if self.port == 465 else smtplib.SMTP
        with smtp_cls(self.host, self.port, timeout=self.timeout) as conn:
            if smtp_cls is smtplib.SMTP:
                conn.starttls()
            if self.username and self.password:
                conn.login(self.username, self.password)
            refused = conn.sendmail(self.from_addr, to, msg.as_string())
            if refused:
                raise RuntimeError(f"SMTP refused recipients: {refused}")


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


def _require_from_addr(env_var: str) -> str:
    value = os.getenv(env_var, "")
    if not value:
        raise RuntimeError(
            f"{env_var} must be set to a verified sender address — no default is used "
            "since an unverified 'reports@localhost'-style address is silently rejected "
            "or spoofable depending on provider."
        )
    return value


def get_mail_adapter() -> MailAdapter:
    smtp_host = os.getenv("SMTP_HOST")
    if smtp_host:
        return SmtpMailAdapter(
            host=smtp_host,
            port=int(os.getenv("SMTP_PORT", "587")),
            username=os.getenv("SMTP_USERNAME", ""),
            password=os.getenv("SMTP_PASSWORD", ""),
            from_addr=_require_from_addr("SMTP_FROM"),
            timeout=float(os.getenv("SMTP_TIMEOUT", "30")),
        )

    resend_key = os.getenv("RESEND_API_KEY")
    if resend_key:
        return ResendMailAdapter(api_key=resend_key, from_addr=_require_from_addr("RESEND_FROM"))

    usesend_key = os.getenv("USESEND_API_KEY")
    if usesend_key:
        return UsesendMailAdapter(
            api_key=usesend_key,
            from_addr=_require_from_addr("USESEND_FROM"),
            base_url=os.getenv("USESEND_BASE_URL", "https://app.usesend.com/api"),
        )

    raise RuntimeError(
        "No mail provider configured — set SMTP_HOST, or RESEND_API_KEY, or USESEND_API_KEY."
    )
