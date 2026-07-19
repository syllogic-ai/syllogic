"""Tests for mail provider selection and send adapters.

Run with:
    cd backend && .venv/bin/pytest tests/test_mail_adapter.py -v
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.integrations.mail_adapter import (  # noqa: E402
    ResendMailAdapter,
    SmtpMailAdapter,
    UsesendMailAdapter,
    get_mail_adapter,
)


def test_smtp_takes_precedence_when_all_configured(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "user")
    monkeypatch.setenv("SMTP_PASSWORD", "pass")
    monkeypatch.setenv("SMTP_FROM", "reports@example.com")
    monkeypatch.setenv("RESEND_API_KEY", "re_123")
    monkeypatch.setenv("USESEND_API_KEY", "us_123")
    adapter = get_mail_adapter()
    assert isinstance(adapter, SmtpMailAdapter)


def test_resend_used_when_smtp_absent(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.setenv("RESEND_API_KEY", "re_123")
    monkeypatch.setenv("RESEND_FROM", "reports@example.com")
    monkeypatch.setenv("USESEND_API_KEY", "us_123")
    adapter = get_mail_adapter()
    assert isinstance(adapter, ResendMailAdapter)


def test_usesend_used_when_only_usesend_configured(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setenv("USESEND_API_KEY", "us_123")
    monkeypatch.setenv("USESEND_FROM", "reports@example.com")
    adapter = get_mail_adapter()
    assert isinstance(adapter, UsesendMailAdapter)


def test_raises_when_nothing_configured(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("USESEND_API_KEY", raising=False)
    try:
        get_mail_adapter()
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "mail provider" in str(e).lower()


def test_smtp_adapter_calls_smtplib():
    with patch("app.integrations.mail_adapter.smtplib.SMTP") as mock_smtp_cls:
        mock_conn = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_conn
        adapter = SmtpMailAdapter(
            host="smtp.example.com", port=587, username="u", password="p", from_addr="reports@example.com"
        )
        adapter.send(["dest@example.com"], "Subject", "<p>hi</p>", "hi")
        mock_conn.starttls.assert_called_once()
        mock_conn.login.assert_called_once_with("u", "p")
        assert mock_conn.sendmail.called


def test_resend_adapter_calls_resend_client():
    with patch("app.integrations.mail_adapter.resend") as mock_resend:
        adapter = ResendMailAdapter(api_key="re_123", from_addr="reports@example.com")
        adapter.send(["dest@example.com"], "Subject", "<p>hi</p>", "hi")
        mock_resend.Emails.send.assert_called_once()


def test_usesend_adapter_calls_http_post():
    with patch("app.integrations.mail_adapter.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, ok=True)
        adapter = UsesendMailAdapter(api_key="us_123", from_addr="reports@example.com", base_url="https://usesend.example.com")
        adapter.send(["dest@example.com"], "Subject", "<p>hi</p>", "hi")
        mock_post.assert_called_once()
