"""Tests for SYL-32 / SYL-29 prompt enrichment."""
from unittest.mock import MagicMock

import pytest

from app.services.category_matcher import CategoryMatcher


class FakeCategory:
    def __init__(self, name, description=None, category_type="expense"):
        self.name = name
        self.description = description
        self.category_type = category_type


class FakeAccount:
    def __init__(self, name, external_id=None, alias_patterns=None):
        self.name = name
        self.external_id = external_id
        self.alias_patterns = alias_patterns or []


def test_render_category_list_with_descriptions():
    m = CategoryMatcher.__new__(CategoryMatcher)  # avoid __init__ for this unit test
    cats = [
        FakeCategory("Side Projects", "Tools used for side projects (Cloudflare, Framer)"),
        FakeCategory("Food & Dining", None),
    ]
    rendered = m._render_category_list(cats)
    assert "- Side Projects — Tools used for side projects (Cloudflare, Framer)" in rendered
    assert "- Food & Dining" in rendered
    assert "None" not in rendered


def test_render_category_list_truncates_long_description():
    m = CategoryMatcher.__new__(CategoryMatcher)
    long = "A" * 500
    rendered = m._render_category_list([FakeCategory("X", long)])
    assert len(rendered) < 300  # bound: name + " — " + 200 chars max


def test_prompt_includes_category_descriptions(monkeypatch, db_session):
    # Use the real CategoryMatcher with a stub DB; assert prompt contains descriptions.
    import app.services.category_matcher as cm_module
    captured = {}

    class StubClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    captured["messages"] = kwargs["messages"]
                    class R:
                        choices = [type("X", (), {"message": type("M", (), {"content": "UNKNOWN"})()})()]
                        usage = type("U", (), {"prompt_tokens": 1, "completion_tokens": 1})()
                    return R()

    m = cm_module.CategoryMatcher(db=db_session, user_id="prompt-user")
    monkeypatch.setattr(m, "_get_openai_client", lambda: StubClient())
    # Also monkeypatch _load_categories so we don't depend on DB having categories
    monkeypatch.setattr(m, "_load_categories", lambda: {})

    cats = [FakeCategory("Side Projects", "Tools like Cloudflare, Framer, GitHub.")]
    m.match_category_llm(
        description="Cloudflare workers",
        merchant="Cloudflare",
        amount=-5.0,
        available_categories=cats,
    )
    prompt_text = captured["messages"][1]["content"]
    assert "Side Projects — Tools like Cloudflare" in prompt_text


def test_account_context_empty_returns_empty_string():
    m = CategoryMatcher.__new__(CategoryMatcher)
    m._account_cache = []
    assert m._build_account_context() == ""


def test_account_context_with_last_four_and_patterns():
    m = CategoryMatcher.__new__(CategoryMatcher)
    m._account_cache = [
        FakeAccount("ABN AMRO checking", external_id="NL91ABNA0417164300"),
        FakeAccount(
            "Revolut Pro",
            external_id=None,
            alias_patterns=["Apple Pay Top-Up by *1234", "Revo Pro"],
        ),
    ]
    ctx = m._build_account_context()
    assert "Your accounts" in ctx
    assert "ABN AMRO checking (ends in 4300)" in ctx
    assert 'Revolut Pro (patterns: "Apple Pay Top-Up by *1234", "Revo Pro")' in ctx
