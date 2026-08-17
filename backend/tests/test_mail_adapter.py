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


def test_smtp_fails_fast_when_from_missing(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.delenv("SMTP_FROM", raising=False)
    try:
        get_mail_adapter()
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "SMTP_FROM" in str(e)


def test_resend_fails_fast_when_from_missing(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.setenv("RESEND_API_KEY", "re_123")
    monkeypatch.delenv("RESEND_FROM", raising=False)
    try:
        get_mail_adapter()
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "RESEND_FROM" in str(e)


def test_usesend_fails_fast_when_from_missing(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setenv("USESEND_API_KEY", "us_123")
    monkeypatch.delenv("USESEND_FROM", raising=False)
    try:
        get_mail_adapter()
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "USESEND_FROM" in str(e)


def test_smtp_adapter_calls_smtplib():
    with patch("app.integrations.mail_adapter.smtplib.SMTP") as mock_smtp_cls:
        mock_conn = MagicMock()
        mock_conn.sendmail.return_value = {}
        mock_smtp_cls.return_value.__enter__.return_value = mock_conn
        adapter = SmtpMailAdapter(
            host="smtp.example.com", port=587, username="u", password="p", from_addr="reports@example.com"
        )
        adapter.send(["dest@example.com"], "Subject", "<p>hi</p>", "hi")
        mock_conn.starttls.assert_called_once()
        mock_conn.login.assert_called_once_with("u", "p")
        assert mock_conn.sendmail.called


def test_smtp_adapter_uses_connect_timeout():
    with patch("app.integrations.mail_adapter.smtplib.SMTP") as mock_smtp_cls:
        mock_conn = MagicMock()
        mock_conn.sendmail.return_value = {}
        mock_smtp_cls.return_value.__enter__.return_value = mock_conn
        adapter = SmtpMailAdapter(
            host="smtp.example.com", port=587, username="u", password="p", from_addr="reports@example.com",
            timeout=5,
        )
        adapter.send(["dest@example.com"], "Subject", "<p>hi</p>", "hi")
        mock_smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=5)


def test_smtp_adapter_default_timeout_is_30():
    with patch("app.integrations.mail_adapter.smtplib.SMTP") as mock_smtp_cls:
        mock_conn = MagicMock()
        mock_conn.sendmail.return_value = {}
        mock_smtp_cls.return_value.__enter__.return_value = mock_conn
        adapter = SmtpMailAdapter(
            host="smtp.example.com", port=587, username="u", password="p", from_addr="reports@example.com",
        )
        adapter.send(["dest@example.com"], "Subject", "<p>hi</p>", "hi")
        mock_smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=30)


def test_smtp_adapter_uses_ssl_on_port_465():
    with patch("app.integrations.mail_adapter.smtplib.SMTP_SSL") as mock_ssl_cls, \
         patch("app.integrations.mail_adapter.smtplib.SMTP") as mock_smtp_cls:
        mock_conn = MagicMock()
        mock_conn.sendmail.return_value = {}
        mock_ssl_cls.return_value.__enter__.return_value = mock_conn
        adapter = SmtpMailAdapter(
            host="smtp.example.com", port=465, username="u", password="p", from_addr="reports@example.com",
        )
        adapter.send(["dest@example.com"], "Subject", "<p>hi</p>", "hi")
        mock_ssl_cls.assert_called_once_with("smtp.example.com", 465, timeout=30)
        mock_smtp_cls.assert_not_called()
        mock_conn.starttls.assert_not_called()
        mock_conn.login.assert_called_once_with("u", "p")


def test_smtp_adapter_skips_login_when_no_credentials():
    with patch("app.integrations.mail_adapter.smtplib.SMTP") as mock_smtp_cls:
        mock_conn = MagicMock()
        mock_conn.sendmail.return_value = {}
        mock_smtp_cls.return_value.__enter__.return_value = mock_conn
        adapter = SmtpMailAdapter(
            host="smtp.example.com", port=587, username="", password="", from_addr="reports@example.com",
        )
        adapter.send(["dest@example.com"], "Subject", "<p>hi</p>", "hi")
        mock_conn.login.assert_not_called()


def test_smtp_adapter_raises_on_refused_recipients():
    with patch("app.integrations.mail_adapter.smtplib.SMTP") as mock_smtp_cls:
        mock_conn = MagicMock()
        mock_conn.sendmail.return_value = {"bad@example.com": (550, b"No such user")}
        mock_smtp_cls.return_value.__enter__.return_value = mock_conn
        adapter = SmtpMailAdapter(
            host="smtp.example.com", port=587, username="u", password="p", from_addr="reports@example.com",
        )
        try:
            adapter.send(["dest@example.com", "bad@example.com"], "Subject", "<p>hi</p>", "hi")
            assert False, "expected RuntimeError"
        except RuntimeError as e:
            assert "refused" in str(e).lower()


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
