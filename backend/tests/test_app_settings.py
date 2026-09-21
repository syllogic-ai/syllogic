import base64

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import AppSetting, User
from app.security.data_encryption import reset_encryption_config_cache
from decimal import Decimal

from app.services.app_settings import (
    clear_ai_summary_enabled,
    clear_llm_model,
    clear_openai_api_key,
    clear_receipt_grocery_category_id,
    clear_receipt_grocery_merchants,
    clear_receipt_treat_split_threshold,
    get_ai_summary_enabled_status,
    get_effective_llm_model,
    get_effective_receipt_grocery_category_id,
    get_effective_receipt_grocery_merchants,
    get_effective_receipt_resolve_config,
    get_effective_receipt_treat_split_threshold,
    get_llm_base_url,
    get_llm_model,
    get_openai_api_key,
    get_openai_api_key_status,
    set_ai_summary_enabled,
    set_llm_model,
    set_openai_api_key,
    set_receipt_grocery_category_id,
    set_receipt_grocery_merchants,
    set_receipt_treat_split_threshold,
)


def _session():
    engine = create_engine("sqlite:///:memory:")
    User.__table__.create(bind=engine)
    AppSetting.__table__.create(bind=engine)
    Session = sessionmaker(bind=engine)
    return Session()


def _set_encryption_key(monkeypatch):
    key = base64.urlsafe_b64encode(b"s" * 32).decode("utf-8").rstrip("=")
    monkeypatch.setenv("DATA_ENCRYPTION_KEY_CURRENT", key)
    monkeypatch.setenv("DATA_ENCRYPTION_KEY_ID", "k-test-app-settings")
    monkeypatch.delenv("DATA_ENCRYPTION_KEY_PREVIOUS", raising=False)
    reset_encryption_config_cache()


def test_openai_api_key_uses_environment_fallback(monkeypatch):
    db = _session()
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("CATEGORIZATION_LLM_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")

    assert get_openai_api_key(db) == "sk-env"
    assert get_openai_api_key_status(db) == {
        "configured": True,
        "source": "environment",
        "database_configured": False,
        "environment_configured": True,
        "base_url": None,
        "model": "gpt-4o-mini",
        "provider": "openai",
    }


def test_provider_neutral_environment_takes_precedence(monkeypatch):
    db = _session()
    monkeypatch.setenv("LLM_API_KEY", "custom-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-legacy")
    monkeypatch.setenv("LLM_BASE_URL", "http://ollama:11434/v1")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://legacy.example/v1")
    monkeypatch.setenv("LLM_MODEL", "qwen3:8b")

    assert get_openai_api_key(db) == "custom-key"
    assert get_llm_base_url() == "http://ollama:11434/v1"
    assert get_llm_model() == "qwen3:8b"
    assert get_openai_api_key_status(db) == {
        "configured": True,
        "source": "environment",
        "database_configured": False,
        "environment_configured": True,
        "base_url": "http://ollama:11434/v1",
        "model": "qwen3:8b",
        "provider": "custom",
    }


def test_custom_endpoint_uses_placeholder_key(monkeypatch):
    db = _session()
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_BASE_URL", "http://localai:8080/v1")

    assert get_openai_api_key(db) == "local-llm"
    assert get_openai_api_key_status(db)["configured"] is True


def test_saved_openai_api_key_overrides_environment(monkeypatch):
    db = _session()
    _set_encryption_key(monkeypatch)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")

    set_openai_api_key(db, "sk-db", updated_by_user_id=None)

    assert get_openai_api_key(db) == "sk-db"
    assert get_openai_api_key_status(db)["source"] == "database"
    stored = db.query(AppSetting).one()
    assert "sk-db" not in stored.value_encrypted


def test_clear_openai_api_key_restores_environment_fallback(monkeypatch):
    db = _session()
    _set_encryption_key(monkeypatch)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")

    set_openai_api_key(db, "sk-db", updated_by_user_id=None)
    clear_openai_api_key(db)

    assert get_openai_api_key(db) == "sk-env"
    assert get_openai_api_key_status(db)["source"] == "environment"


def test_llm_model_override_takes_precedence_over_env(monkeypatch):
    db = _session()
    _set_encryption_key(monkeypatch)
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")

    assert get_effective_llm_model(db) == "gpt-4o-mini"

    set_llm_model(db, "gpt-4o", updated_by_user_id=None)
    assert get_effective_llm_model(db) == "gpt-4o"

    clear_llm_model(db)
    assert get_effective_llm_model(db) == "gpt-4o-mini"


def test_set_llm_model_rejects_blank_value(monkeypatch):
    db = _session()
    _set_encryption_key(monkeypatch)

    with pytest.raises(ValueError):
        set_llm_model(db, "   ", updated_by_user_id=None)


def test_ai_summary_enabled_defaults_off_then_toggles(monkeypatch):
    db = _session()
    _set_encryption_key(monkeypatch)

    assert get_ai_summary_enabled_status(db) == {"enabled": False, "source": "default"}

    set_ai_summary_enabled(db, True, updated_by_user_id=None)
    assert get_ai_summary_enabled_status(db) == {"enabled": True, "source": "database"}

    clear_ai_summary_enabled(db)
    assert get_ai_summary_enabled_status(db) == {"enabled": False, "source": "default"}


# --- Receipt-resolve config (Phase 6.1) ------------------------------------


def test_receipt_grocery_merchants_defaults_empty_then_env_then_db_override(monkeypatch):
    db = _session()
    _set_encryption_key(monkeypatch)
    monkeypatch.delenv("RECEIPT_GROCERY_MERCHANTS", raising=False)

    assert get_effective_receipt_grocery_merchants(db) == frozenset()

    monkeypatch.setenv("RECEIPT_GROCERY_MERCHANTS", "Rimi, Maxima")
    assert get_effective_receipt_grocery_merchants(db) == frozenset({"rimi", "maxima"})

    set_receipt_grocery_merchants(db, ["Lidl"], updated_by_user_id=None)
    assert get_effective_receipt_grocery_merchants(db) == frozenset({"lidl"})

    clear_receipt_grocery_merchants(db)
    assert get_effective_receipt_grocery_merchants(db) == frozenset({"rimi", "maxima"})


def test_receipt_grocery_category_id_db_override_wins_over_env(monkeypatch):
    db = _session()
    _set_encryption_key(monkeypatch)
    monkeypatch.delenv("RECEIPT_GROCERY_CATEGORY_ID", raising=False)

    assert get_effective_receipt_grocery_category_id(db) is None

    monkeypatch.setenv("RECEIPT_GROCERY_CATEGORY_ID", "cat-from-env")
    assert get_effective_receipt_grocery_category_id(db) == "cat-from-env"

    set_receipt_grocery_category_id(db, "cat-from-db", updated_by_user_id=None)
    assert get_effective_receipt_grocery_category_id(db) == "cat-from-db"

    clear_receipt_grocery_category_id(db)
    assert get_effective_receipt_grocery_category_id(db) == "cat-from-env"


def test_receipt_treat_split_threshold_none_disables_by_default(monkeypatch):
    db = _session()
    _set_encryption_key(monkeypatch)
    monkeypatch.delenv("RECEIPT_TREAT_SPLIT_THRESHOLD", raising=False)

    assert get_effective_receipt_treat_split_threshold(db) is None

    monkeypatch.setenv("RECEIPT_TREAT_SPLIT_THRESHOLD", "5.00")
    assert get_effective_receipt_treat_split_threshold(db) == Decimal("5.00")

    set_receipt_treat_split_threshold(db, Decimal("3.50"), updated_by_user_id=None)
    assert get_effective_receipt_treat_split_threshold(db) == Decimal("3.50")

    # An explicit DB-stored `None` overrides even a non-empty env value --
    # distinct from "no row", which falls through to env.
    set_receipt_treat_split_threshold(db, None, updated_by_user_id=None)
    assert get_effective_receipt_treat_split_threshold(db) is None

    clear_receipt_treat_split_threshold(db)
    assert get_effective_receipt_treat_split_threshold(db) == Decimal("5.00")


def test_effective_receipt_resolve_config_bundles_all_three(monkeypatch):
    db = _session()
    _set_encryption_key(monkeypatch)
    monkeypatch.delenv("RECEIPT_GROCERY_MERCHANTS", raising=False)
    monkeypatch.delenv("RECEIPT_GROCERY_CATEGORY_ID", raising=False)
    monkeypatch.delenv("RECEIPT_TREAT_SPLIT_THRESHOLD", raising=False)

    set_receipt_grocery_merchants(db, ["Rimi"], updated_by_user_id=None)
    set_receipt_grocery_category_id(db, "cat-groceries", updated_by_user_id=None)
    set_receipt_treat_split_threshold(db, Decimal("5.00"), updated_by_user_id=None)

    config = get_effective_receipt_resolve_config(db)
    assert config == {
        "grocery_merchants": frozenset({"rimi"}),
        "grocery_category_id": "cat-groceries",
        "treat_split_threshold": Decimal("5.00"),
    }
