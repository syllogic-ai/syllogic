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


def test_prompt_includes_account_context_and_transfer_rule(monkeypatch, db_session):
    import app.services.category_matcher as cm_module
    captured = {}

    _stub_response = type("R", (), {
        "choices": [type("X", (), {"message": type("M", (), {"content": "UNKNOWN"})()})()],
        "usage": type("U", (), {"prompt_tokens": 1, "completion_tokens": 1})(),
    })

    class StubClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    captured["messages"] = kwargs["messages"]
                    return _stub_response

    m = cm_module.CategoryMatcher(db=db_session, user_id="tr-user")
    monkeypatch.setattr(m, "_get_openai_client", lambda: StubClient())
    monkeypatch.setattr(m, "_load_categories", lambda: {})
    m._account_cache = [
        FakeAccount("Revolut Pro", alias_patterns=["Apple Pay Top-Up by *1234"])
    ]
    cats = [FakeCategory("Transfers", "Internal transfers", category_type="transfer")]
    m.match_category_llm(
        description="Apple Pay Top-Up by *1234",
        merchant="Revolut",
        amount=-50.0,
        available_categories=cats,
    )
    prompt = captured["messages"][1]["content"]
    assert "Your accounts" in prompt
    assert "Apple Pay Top-Up by *1234" in prompt
    assert "internal transfer" in prompt.lower()


def test_prompt_instructions_numbered_correctly_without_accounts(monkeypatch, db_session):
    import app.services.category_matcher as cm_module
    captured = {}

    _stub_response = type("R", (), {
        "choices": [type("X", (), {"message": type("M", (), {"content": "UNKNOWN"})()})()],
        "usage": type("U", (), {"prompt_tokens": 1, "completion_tokens": 1})(),
    })

    class StubClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    captured["messages"] = kwargs["messages"]
                    return _stub_response

    m = cm_module.CategoryMatcher(db=db_session, user_id="no-acct-user")
    monkeypatch.setattr(m, "_get_openai_client", lambda: StubClient())
    monkeypatch.setattr(m, "_load_categories", lambda: {})
    # Explicitly set no accounts so transfer_rule is empty
    m._account_cache = []

    cats = [FakeCategory("Groceries", "Food and drink", category_type="expense")]
    m.match_category_llm(
        description="ALBERT HEIJN 1234",
        merchant="Albert Heijn",
        amount=-15.0,
        available_categories=cats,
    )
    prompt = captured["messages"][1]["content"]

    # No account context should appear
    assert "Your accounts" not in prompt

    # The merged "3. 4." pattern must not appear anywhere
    assert "3. 4." not in prompt

    # Without accounts, the list is 6 items (no transfer rule injected)
    # Items 3 and 4 should be the follow-up instructions, not a blank + merged line
    assert "3. Follow any user-specific guidelines" in prompt
    assert "4. If the transaction matches a user override" in prompt
    assert "5. Respond with ONLY the exact category name" in prompt
    assert '6. If no category fits well, respond with "UNKNOWN"' in prompt


# ---------------------------------------------------------------------------
# Task 8: Prompt budget degradation
# ---------------------------------------------------------------------------

def test_prompt_budget_degrades_descriptions_first():
    m = CategoryMatcher.__new__(CategoryMatcher)
    # Simulate oversized input: 30 categories each with a 200-char description.
    cats = [FakeCategory(f"Cat{i}", "x" * 200) for i in range(30)]
    m._account_cache = [FakeAccount("Acc", alias_patterns=["p1", "p2"])]
    category_list, account_block = m._compose_prompt_context(cats)
    assert sum(len(x) for x in (category_list, account_block)) <= 2000
    # Descriptions dropped, but names always present
    assert "Cat0" in category_list
    assert "Cat29" in category_list


def test_prompt_budget_stage4_drops_account_block_when_still_oversized():
    """Stage-4: when name_only + thin_account_block still exceeds the budget,
    the account block must be dropped entirely so the output is always <= 2000 chars.
    """
    m = CategoryMatcher.__new__(CategoryMatcher)
    # 100 categories with long names → name_only alone approaches the budget
    cats = [FakeCategory(f"Category With A Very Long Name {i:03d}") for i in range(100)]
    # 50 accounts → thin_account_block adds several hundred characters
    m._account_cache = [
        FakeAccount(f"Account Bank Name {j:02d}", external_id=f"NL91ABNA{j:08d}")
        for j in range(50)
    ]
    category_list, account_block = m._compose_prompt_context(cats)
    total = sum(len(x) for x in (category_list, account_block))
    assert total <= 2000, (
        f"Output exceeded budget ({total} chars); stage-4 fallback not applied"
    )
    # Category names must still be present
    assert "Category With A Very Long Name 000" in category_list


# ---------------------------------------------------------------------------
# Task 9: Feature flag
# ---------------------------------------------------------------------------

def test_feature_flag_disabled_falls_back_to_names_only(monkeypatch, db_session):
    import app.services.category_matcher as cm_module
    monkeypatch.setattr(cm_module, "ENRICHED_PROMPT_ENABLED", False)
    captured = {}

    _stub_response = type("R", (), {
        "choices": [type("X", (), {"message": type("M", (), {"content": "UNKNOWN"})()})()],
        "usage": type("U", (), {"prompt_tokens": 1, "completion_tokens": 1})(),
    })

    class StubClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    captured["messages"] = kwargs["messages"]
                    return _stub_response

    m = cm_module.CategoryMatcher(db=db_session, user_id="ff-user")
    monkeypatch.setattr(m, "_get_openai_client", lambda: StubClient())
    monkeypatch.setattr(m, "_load_categories", lambda: {})
    m._account_cache = [FakeAccount("Acc", alias_patterns=["p"])]
    cats = [FakeCategory("Food", "Description here")]
    m.match_category_llm(description="x", merchant="y", amount=-1.0, available_categories=cats)
    prompt = captured["messages"][1]["content"]
    assert "Description here" not in prompt
    assert "Your accounts" not in prompt
