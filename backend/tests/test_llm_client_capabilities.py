"""Tests for provider capability resolution and filtering in
`app.services.llm_client` (Phase 3 of the receipt-ingestion rework).

These tests stub out `create_llm_client` / `create_llm_fallback_client` and
the model-lookup helpers rather than touching the database or the `openai`
package -- capability resolution is pure logic layered on top of whichever
clients those functions hand back.
"""

from types import SimpleNamespace

import pytest

from app.services import llm_client
from app.services.llm_client import LLMProvider, NoCapableProviderError


def _stub_both_providers(monkeypatch, *, primary_model="gpt-4o-mini", fallback_model="llama3"):
    """Configure both a primary and a fallback client with the given models."""
    monkeypatch.setattr(
        llm_client, "create_llm_client", lambda db: SimpleNamespace(name="primary-client")
    )
    monkeypatch.setattr(llm_client, "get_effective_llm_model", lambda db: primary_model)
    monkeypatch.setattr(
        llm_client, "create_llm_fallback_client", lambda: SimpleNamespace(name="fallback-client")
    )
    monkeypatch.setattr(llm_client, "get_llm_fallback_model", lambda: fallback_model)


def _stub_primary_only(monkeypatch, *, primary_model="gpt-4o-mini"):
    monkeypatch.setattr(
        llm_client, "create_llm_client", lambda db: SimpleNamespace(name="primary-client")
    )
    monkeypatch.setattr(llm_client, "get_effective_llm_model", lambda db: primary_model)
    monkeypatch.setattr(llm_client, "create_llm_fallback_client", lambda: None)


def _clear_capability_env(monkeypatch):
    for name in (
        "LLM_VISION_CAPABLE",
        "LLM_STRICT_SCHEMA_CAPABLE",
        "LLM_FALLBACK_VISION_CAPABLE",
        "LLM_FALLBACK_STRICT_SCHEMA_CAPABLE",
    ):
        monkeypatch.delenv(name, raising=False)


# ---------------------------------------------------------------------------
# Existing callers (no `requires`) see unchanged behaviour
# ---------------------------------------------------------------------------


def test_no_requires_returns_same_providers_as_before(monkeypatch):
    """Callers passing no `requires` (every caller in the repo before this
    change) get exactly the providers they got before -- capability fields
    ride along but never filter anything out."""
    _clear_capability_env(monkeypatch)
    _stub_both_providers(monkeypatch)

    providers = llm_client.create_llm_clients(object())

    assert [p.label for p in providers] == ["primary", "fallback"]
    assert providers[0].model == "gpt-4o-mini"
    assert providers[1].model == "llama3"
    assert all(isinstance(p, LLMProvider) for p in providers)


def test_no_requires_with_no_providers_configured_returns_empty_list(monkeypatch):
    """An empty result is only an error when `requires` is non-empty --
    the no-configuration case must still be the plain empty list every
    existing caller (e.g. `_generate_narrative`) already checks for."""
    _clear_capability_env(monkeypatch)
    monkeypatch.setattr(llm_client, "create_llm_client", lambda db: None)
    monkeypatch.setattr(llm_client, "create_llm_fallback_client", lambda: None)

    providers = llm_client.create_llm_clients(object())

    assert providers == []


# ---------------------------------------------------------------------------
# Capability resolution and filtering
# ---------------------------------------------------------------------------


def test_fallback_excluded_from_vision_request_by_default(monkeypatch):
    """The fallback provider (an unconfigured local model, by default) is
    excluded from a vision-required request unless something says it can
    handle images."""
    _clear_capability_env(monkeypatch)
    _stub_both_providers(monkeypatch, fallback_model="some-local-model")

    providers = llm_client.create_llm_clients(object(), requires=frozenset({"vision"}))

    assert [p.label for p in providers] == ["primary"]
    assert providers[0].supports_vision is True


def test_env_override_includes_fallback_in_vision_request(monkeypatch):
    """An explicit `LLM_FALLBACK_VISION_CAPABLE=true` override brings the
    fallback provider back into a vision-required filter."""
    _clear_capability_env(monkeypatch)
    monkeypatch.setenv("LLM_FALLBACK_VISION_CAPABLE", "true")
    _stub_both_providers(monkeypatch, fallback_model="some-local-model")

    providers = llm_client.create_llm_clients(object(), requires=frozenset({"vision"}))

    assert [p.label for p in providers] == ["primary", "fallback"]
    assert providers[1].supports_vision is True


def test_env_override_can_disable_primary_capability(monkeypatch):
    """The override also works in the other direction: it can mark an
    otherwise-allowlisted primary model as not vision-capable."""
    _clear_capability_env(monkeypatch)
    monkeypatch.setenv("LLM_VISION_CAPABLE", "false")
    _stub_primary_only(monkeypatch, primary_model="gpt-4o-mini")

    with pytest.raises(NoCapableProviderError):
        llm_client.create_llm_clients(object(), requires=frozenset({"vision"}))


def test_known_model_allowlist_grants_capability_without_override(monkeypatch):
    """A primary on a known vision+strict-schema model (no env override at
    all) satisfies both capabilities via the allowlist, not just the
    primary-defaults-True rule -- pin this down with a model that would only
    pass because it matches the allowlist."""
    _clear_capability_env(monkeypatch)
    _stub_primary_only(monkeypatch, primary_model="gpt-4.1-mini")

    providers = llm_client.create_llm_clients(
        object(), requires=frozenset({"vision", "strict_schema"})
    )

    assert len(providers) == 1
    assert providers[0].supports_vision is True
    assert providers[0].supports_strict_schema is True


def test_unknown_fallback_model_defaults_to_not_capable(monkeypatch):
    _clear_capability_env(monkeypatch)
    _stub_both_providers(monkeypatch, fallback_model="totally-unknown-model")

    providers = llm_client.create_llm_clients(object())
    fallback = providers[1]

    assert fallback.supports_vision is False
    assert fallback.supports_strict_schema is False


def test_empty_filtered_result_raises_named_error_not_empty_list(monkeypatch):
    """When providers exist but none satisfy `requires`, the caller gets a
    named, actionable error -- never a silent empty list."""
    _clear_capability_env(monkeypatch)
    # Only a fallback provider, on a model with no known capabilities, and no
    # override -- filtering on strict_schema leaves nothing.
    monkeypatch.setattr(llm_client, "create_llm_client", lambda db: None)
    monkeypatch.setattr(
        llm_client, "create_llm_fallback_client", lambda: SimpleNamespace(name="fallback-client")
    )
    monkeypatch.setattr(llm_client, "get_llm_fallback_model", lambda: "some-local-model")

    with pytest.raises(NoCapableProviderError) as exc_info:
        llm_client.create_llm_clients(object(), requires=frozenset({"strict_schema"}))

    assert "strict_schema" in str(exc_info.value)


@pytest.mark.parametrize(
    "model",
    [
        "claude-3-5-sonnet-20241022",
        "gemini-1.5-pro",
        "qwen2-vl-7b-instruct",
        "llava-1.6-34b",
        "minicpm-v-8b",
        "pixtral-12b",
        "mistral-small-3.1-24b-instruct",
    ],
)
def test_non_openai_vision_models_are_recognized_by_the_extended_allowlist(monkeypatch, model):
    """Spec 4.0: the allowlist is extended beyond OpenAI prefixes so a
    non-OpenAI fallback provider (e.g. a local Ollama server running one of
    these) doesn't need an env override just to be considered for a
    vision-required request."""
    _clear_capability_env(monkeypatch)
    _stub_both_providers(monkeypatch, fallback_model=model)

    providers = llm_client.create_llm_clients(object(), requires=frozenset({"vision"}))

    assert [p.label for p in providers] == ["primary", "fallback"]
    assert providers[1].supports_vision is True


def test_openrouter_style_vendor_prefix_is_stripped_before_matching(monkeypatch):
    """An OpenRouter-style "vendor/model" id (e.g. "anthropic/claude-3-5-
    sonnet") should resolve capability the same as the bare model id."""
    _clear_capability_env(monkeypatch)
    _stub_both_providers(monkeypatch, fallback_model="anthropic/claude-3-5-sonnet")

    providers = llm_client.create_llm_clients(
        object(), requires=frozenset({"vision", "strict_schema"})
    )

    assert [p.label for p in providers] == ["primary", "fallback"]
    assert providers[1].supports_vision is True
    assert providers[1].supports_strict_schema is True


def test_qwen_vl_glob_does_not_match_a_non_vl_qwen_model(monkeypatch):
    """ "qwen*-vl" is a real glob (not just a prefix) -- a plain text-only
    Qwen model must not match it."""
    _clear_capability_env(monkeypatch)
    _stub_both_providers(monkeypatch, fallback_model="qwen2.5-72b-instruct")

    providers = llm_client.create_llm_clients(object(), requires=frozenset({"vision"}))

    assert [p.label for p in providers] == ["primary"]


def test_requires_filters_out_provider_missing_only_one_capability(monkeypatch):
    """A provider must satisfy *every* requested capability, not just one."""
    _clear_capability_env(monkeypatch)
    monkeypatch.setenv("LLM_STRICT_SCHEMA_CAPABLE", "false")
    _stub_primary_only(monkeypatch, primary_model="gpt-4o-mini")

    with pytest.raises(NoCapableProviderError):
        llm_client.create_llm_clients(object(), requires=frozenset({"vision", "strict_schema"}))

    # But it's still returned for a request that only needs the capability
    # it does have.
    providers = llm_client.create_llm_clients(object(), requires=frozenset({"vision"}))
    assert len(providers) == 1
