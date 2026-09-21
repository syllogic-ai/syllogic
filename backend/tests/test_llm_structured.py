"""Tests for `app.services.llm_structured` -- the shared structured-output
helper, including the model-agnosticism response-format ladder from spec 4.0.

`response_format={"type": "json_schema", "strict": True}` is an OpenAI
extension; a provider that rejects it (Ollama, Anthropic's OpenAI-compat
layer, older vLLM, many OpenRouter models) 400s naming the valid
`response_format` values. These tests simulate exactly that and assert
`call_structured` degrades the request shape against the *same* provider
before ever considering a fallback provider.
"""

import json

import pytest

from app.services import llm_structured
from app.services.llm_client import LLMProvider
from app.services.llm_structured import (
    SchemaValidationError,
    StructuredCallError,
    call_structured,
)

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name"],
    "properties": {"name": {"type": "string"}},
}


@pytest.fixture(autouse=True)
def _reset_rung_cache():
    """The rung cache is process-lifetime by design -- reset it between
    tests so one test's provider degradation doesn't leak into the next."""
    llm_structured.reset_rung_cache()
    yield
    llm_structured.reset_rung_cache()


class _FakeMessage:
    def __init__(self, content, refusal=None):
        self.content = content
        self.refusal = refusal


class _FakeChoice:
    def __init__(self, message):
        self.message = message


class _FakeResponse:
    def __init__(self, content, refusal=None):
        self.choices = [_FakeChoice(_FakeMessage(content, refusal))]


class _Completions:
    """Minimal stand-in for `client.chat.completions`: `create` is delegated
    to a plain function so each fake client can define its own behaviour
    without fighting Python's `self` shadowing rules in a nested class."""

    def __init__(self, create_fn):
        self._create_fn = create_fn

    def create(self, **kwargs):
        return self._create_fn(**kwargs)


class _Chat:
    def __init__(self, create_fn):
        self.completions = _Completions(create_fn)


class _ResponseFormatRejectingClient:
    """Simulates a provider that 400s on any `response_format` it doesn't
    recognize -- rejects json_schema, but accepts json_object, and always
    accepts a bare call with no response_format at all."""

    def __init__(self, rejects=("json_schema",), payload=None):
        self.rejects = set(rejects)
        self.payload = payload if payload is not None else {"name": "ok"}
        self.calls: list[dict] = []
        self.chat = _Chat(self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        response_format = kwargs.get("response_format")
        rf_type = (response_format or {}).get("type") if response_format else None
        if rf_type == "json_schema" and "json_schema" in self.rejects:
            raise RuntimeError(
                "400 Bad Request: 'response_format' of type 'json_schema' "
                "is not one of ['text', 'json_object']"
            )
        if rf_type == "json_object" and "json_object" in self.rejects:
            raise RuntimeError("400 Bad Request: 'response_format' is not a supported parameter")
        return _FakeResponse(json.dumps(self.payload))


class _AlwaysFailsClient:
    def __init__(self, error: Exception):
        self.error = error
        self.calls = 0
        self.chat = _Chat(self._create)

    def _create(self, **kwargs):
        self.calls += 1
        raise self.error


class _AlwaysSucceedsClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls: list[dict] = []
        self.chat = _Chat(self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(json.dumps(self.payload))


def _provider(client, label="primary", model="local-model"):
    return LLMProvider(
        client=client,
        model=model,
        label=label,
        supports_vision=True,
        supports_strict_schema=True,
    )


# ---------------------------------------------------------------------------
# Rung 1 (json_schema) succeeds -- unchanged from before the ladder existed
# ---------------------------------------------------------------------------


def test_json_schema_rung_succeeds_on_a_capable_provider():
    client = _AlwaysSucceedsClient({"name": "ok"})
    payload, model = call_structured(
        [_provider(client)],
        messages=[{"role": "user", "content": "go"}],
        schema=SCHEMA,
        schema_name="thing",
        max_tokens=100,
        timeout=10,
    )
    assert payload == {"name": "ok"}
    assert model == "local-model"
    assert client.calls[0]["response_format"]["type"] == "json_schema"


# ---------------------------------------------------------------------------
# The core 4.0 requirement: step down within the SAME provider
# ---------------------------------------------------------------------------


def test_steps_down_to_json_object_when_json_schema_is_rejected():
    client = _ResponseFormatRejectingClient(rejects=("json_schema",))
    provider = _provider(client, label="primary")

    payload, model = call_structured(
        [provider],
        messages=[{"role": "user", "content": "go"}],
        schema=SCHEMA,
        schema_name="thing",
        max_tokens=100,
        timeout=10,
    )

    assert payload == {"name": "ok"}
    assert model == provider.model
    # Two calls against the SAME provider: rung 1 rejected, rung 2 succeeded.
    assert len(client.calls) == 2
    assert client.calls[0]["response_format"]["type"] == "json_schema"
    assert client.calls[1]["response_format"]["type"] == "json_object"


def test_steps_all_the_way_down_to_no_response_format_when_both_are_rejected():
    client = _ResponseFormatRejectingClient(rejects=("json_schema", "json_object"))
    provider = _provider(client, label="primary")

    payload, model = call_structured(
        [provider],
        messages=[{"role": "user", "content": "go"}],
        schema=SCHEMA,
        schema_name="thing",
        max_tokens=100,
        timeout=10,
    )

    assert payload == {"name": "ok"}
    assert len(client.calls) == 3
    assert client.calls[0]["response_format"]["type"] == "json_schema"
    assert client.calls[1]["response_format"]["type"] == "json_object"
    assert "response_format" not in client.calls[2]
    # The schema is inlined into the prompt at the weaker rungs.
    assert any("JSON Schema" in str(m.get("content")) for m in client.calls[2]["messages"])


def test_ladder_never_touches_the_fallback_provider_when_the_primary_recovers():
    primary_client = _ResponseFormatRejectingClient(rejects=("json_schema",))
    fallback_client = _AlwaysSucceedsClient({"name": "fallback-should-not-be-used"})
    providers = [
        _provider(primary_client, label="primary", model="primary-model"),
        _provider(fallback_client, label="fallback", model="fallback-model"),
    ]

    payload, model = call_structured(
        providers,
        messages=[{"role": "user", "content": "go"}],
        schema=SCHEMA,
        schema_name="thing",
        max_tokens=100,
        timeout=10,
    )

    assert model == "primary-model"
    assert payload == {"name": "ok"}
    assert fallback_client.calls == []


# ---------------------------------------------------------------------------
# Caching the working rung per provider for the process lifetime
# ---------------------------------------------------------------------------


def test_working_rung_is_cached_and_not_reprobed_on_the_next_call():
    client = _ResponseFormatRejectingClient(rejects=("json_schema",))
    provider = _provider(client, label="primary", model="cached-model")

    call_structured(
        [provider],
        messages=[{"role": "user", "content": "go"}],
        schema=SCHEMA,
        schema_name="thing",
        max_tokens=100,
        timeout=10,
    )
    assert len(client.calls) == 2  # rung 1 rejected, rung 2 succeeded

    # Second call against the same provider: should start straight at the
    # cached rung (json_object), not re-probe json_schema first.
    call_structured(
        [provider],
        messages=[{"role": "user", "content": "go again"}],
        schema=SCHEMA,
        schema_name="thing",
        max_tokens=100,
        timeout=10,
    )
    assert len(client.calls) == 3  # only one more call, straight at rung 2
    assert client.calls[2]["response_format"]["type"] == "json_object"


# ---------------------------------------------------------------------------
# Schema validation still runs at every rung
# ---------------------------------------------------------------------------


def test_schema_validation_runs_even_at_the_weakest_rung():
    client = _ResponseFormatRejectingClient(
        rejects=("json_schema", "json_object"), payload={"wrong_field": 1}
    )
    provider = _provider(client, label="primary")

    # `call_structured` always raises the base `StructuredCallError` at the
    # top level (chaining the real cause via `from`) -- matching the
    # pre-ladder behaviour of this function. The important assertion is that
    # a schema-invalid payload at rung 3 (no response_format enforcement at
    # all) is still caught, not silently accepted.
    with pytest.raises(StructuredCallError) as exc_info:
        call_structured(
            [provider],
            messages=[{"role": "user", "content": "go"}],
            schema=SCHEMA,
            schema_name="thing",
            max_tokens=100,
            timeout=10,
        )
    assert isinstance(exc_info.value.__cause__, SchemaValidationError)
    # All three rungs were attempted -- the weakest rung's schema failure
    # isn't a response_format rejection, so there's no fourth rung to try.
    assert len(client.calls) == 3


# ---------------------------------------------------------------------------
# Non-response_format failures still behave like before the ladder existed
# ---------------------------------------------------------------------------


def test_quota_error_still_advances_to_fallback_provider():
    primary_client = _AlwaysFailsClient(RuntimeError("429 rate limit exceeded"))
    fallback_client = _AlwaysSucceedsClient({"name": "from-fallback"})
    providers = [
        _provider(primary_client, label="primary", model="primary-model"),
        _provider(fallback_client, label="fallback", model="fallback-model"),
    ]

    payload, model = call_structured(
        providers,
        messages=[{"role": "user", "content": "go"}],
        schema=SCHEMA,
        schema_name="thing",
        max_tokens=100,
        timeout=10,
    )
    assert model == "fallback-model"
    assert payload == {"name": "from-fallback"}
    # Only rung 1 was attempted against the primary before advancing -- a
    # 429 isn't a response_format rejection, so no ladder stepping happened.
    assert primary_client.calls == 1


def test_non_response_format_non_fallback_worthy_error_stops_without_trying_fallback():
    primary_client = _AlwaysFailsClient(RuntimeError("the model refused politely"))
    fallback_client = _AlwaysSucceedsClient({"name": "should-not-be-reached"})
    providers = [
        _provider(primary_client, label="primary"),
        _provider(fallback_client, label="fallback"),
    ]

    with pytest.raises(StructuredCallError):
        call_structured(
            providers,
            messages=[{"role": "user", "content": "go"}],
            schema=SCHEMA,
            schema_name="thing",
            max_tokens=100,
            timeout=10,
        )
    assert fallback_client.calls == []


def test_no_providers_raises_structured_call_error():
    with pytest.raises(StructuredCallError):
        call_structured(
            [],
            messages=[{"role": "user", "content": "go"}],
            schema=SCHEMA,
            schema_name="thing",
            max_tokens=100,
            timeout=10,
        )
