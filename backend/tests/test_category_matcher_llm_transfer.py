"""Verify that with an alias-matched account, the LLM prompt steers toward the transfer category."""
from decimal import Decimal

import pytest

from app.services.category_matcher import CategoryMatcher


class FakeCategory:
    def __init__(self, name, category_type="expense"):
        self.name = name
        self.category_type = category_type
        self.description = None


class FakeAccount:
    def __init__(self, name, alias_patterns=None):
        self.name = name
        self.external_id = None
        self.alias_patterns = alias_patterns or []
        self.is_active = True


def test_llm_selects_transfers_when_alias_matches(monkeypatch, db_session):
    import app.services.category_matcher as cm_module
    monkeypatch.setattr(cm_module, "ENRICHED_PROMPT_ENABLED", True)

    class StubClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    # The stub "reads" the prompt: if it mentions the alias + transfer rule,
                    # return the transfer category name.
                    content = kwargs["messages"][1]["content"]
                    if "Apple Pay Top-Up by *1234" in content and "internal transfer" in content.lower():
                        answer = "Transfers"
                    else:
                        answer = "UNKNOWN"
                    return type("R", (), {
                        "choices": [type("X", (), {"message": type("M", (), {"content": answer})()})()],
                        "usage": type("U", (), {"prompt_tokens": 1, "completion_tokens": 1})(),
                    })

    m = CategoryMatcher(db=db_session, user_id="llm-user")
    monkeypatch.setattr(m, "_get_openai_client", lambda: StubClient())
    monkeypatch.setattr(m, "_load_categories", lambda: {})
    m._account_cache = [FakeAccount("Revolut Pro", alias_patterns=["Apple Pay Top-Up by *1234"])]
    cats = [FakeCategory("Transfers", category_type="transfer"), FakeCategory("Food & Dining")]
    result = m.match_category_llm(
        description="Apple Pay Top-Up by *1234",
        merchant="Revolut",
        amount=-50.0,
        available_categories=cats,
    )
    # match_category_llm returns the matched category object, not the name string
    assert result is not None
    assert result.name == "Transfers"
