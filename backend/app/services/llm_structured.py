"""
Shared structured-output helper for LLM calls that need a validated JSON
response: send a schema-guided request against an ordered list of
`LLMProvider`s, parse the result, and raise if it can't be made to fit the
requested shape.

This exists so Phase 4 (receipt extraction) and Phase 5 (receipt
categorization) don't each reimplement the same provider loop, fenced-JSON
tolerance, and schema check. Phase 3 only builds this plumbing — nothing in
this module knows about receipts.

**Model-agnosticism (spec 4.0).** `response_format={"type": "json_schema",
"strict": True}` is an OpenAI extension. Ollama, Anthropic's OpenAI-compat
layer, older vLLM, and many OpenRouter models reject it with a 400 naming the
valid `response_format` types -- a failure `is_fallback_worthy_error` does not
recognize, so without the ladder below the whole call hard-fails with no
degradation. `call_structured` instead steps down a three-rung ladder *within
a provider* before ever considering the next provider:

  1. ``{"type": "json_schema", "strict": true, "schema": ...}`` -- preferred.
  2. ``{"type": "json_object"}`` with the schema inlined into a system message.
  3. No ``response_format`` at all, schema in the prompt, relying on the
     fenced-JSON tolerance in `_parse_json_payload`.

Schema validation runs on the parsed payload at every rung -- a weaker rung
gives a weaker guarantee about the *request* and the same guarantee about the
*result*. The working rung is cached per provider (`label:model`) for the
process lifetime so a provider already known to reject `json_schema` isn't
re-probed on every call.
"""

import json
import logging
from typing import Any, List, Optional, Tuple

from app.services.llm_client import LLMProvider, is_fallback_worthy_error

logger = logging.getLogger(__name__)

# Rungs of the response-format ladder, weakest guarantee last.
RUNG_JSON_SCHEMA = 0
RUNG_JSON_OBJECT = 1
RUNG_NONE = 2
_RUNGS = (RUNG_JSON_SCHEMA, RUNG_JSON_OBJECT, RUNG_NONE)
_RUNG_NAMES = {
    RUNG_JSON_SCHEMA: "json_schema",
    RUNG_JSON_OBJECT: "json_object",
    RUNG_NONE: "none",
}

# Cache of the lowest rung known to work for a given provider, keyed by
# "label:model" -- e.g. "primary:llama3". Process-lifetime only, deliberately
# module-level: this is what makes the ladder "do not re-probe on every
# call". A provider is never assumed to *regress* to a stricter rung once a
# weaker one has been observed to work.
_provider_rung_cache: dict[str, int] = {}


def reset_rung_cache() -> None:
    """Test hook: clear the process-lifetime rung cache."""
    _provider_rung_cache.clear()


def _provider_cache_key(provider: LLMProvider) -> str:
    return f"{provider.label}:{provider.model}"


class StructuredCallError(RuntimeError):
    """Raised when every provider fails, refuses, or returns a response that
    does not validate against the requested schema."""


class SchemaValidationError(StructuredCallError):
    """Raised when a provider's response parses as JSON but does not match
    the requested schema shape."""


def _strip_code_fence(text: str) -> str:
    """Tolerate a fenced-JSON response even when `response_format` was sent.

    Some OpenAI-compatible endpoints accept `response_format` but still wrap
    the output in a ``` code fence (with or without a `json` language tag).
    Copied from the fenced-JSON tolerance that used to live in
    `receipt_ocr.py:_parse_llm_items` rather than imported — that module was
    deleted in Phase 4 (replaced by `receipt_extract.py`).
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:]
    return stripped.strip()


def _parse_json_payload(content: str) -> Any:
    """Parse `content` as JSON, tolerating a fenced wrapper. Raises
    `StructuredCallError` if it can't be parsed either way."""
    text = (content or "").strip()
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass

    fenced = _strip_code_fence(text)
    if fenced != text:
        try:
            return json.loads(fenced)
        except (ValueError, TypeError):
            pass

    raise StructuredCallError(f"LLM response was not valid JSON: {text[:200]!r}")


def _validate_type(value: Any, expected: Any, path: str) -> None:
    type_map = {
        "object": dict,
        "array": list,
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "null": type(None),
    }

    expected_types = expected if isinstance(expected, list) else [expected]
    python_types = tuple(type_map[t] for t in expected_types if t in type_map)
    if python_types and not isinstance(value, python_types):
        # bool is a subclass of int in Python; don't let an int satisfy a
        # "boolean" schema or vice versa unless the schema actually says so.
        if not (
            isinstance(value, bool) and int in python_types and "boolean" not in expected_types
        ):
            raise SchemaValidationError(
                f"{path}: expected {expected_types}, got {type(value).__name__}"
            )


def _validate_against_schema(value: Any, schema: dict, path: str = "$") -> None:
    """A deliberately shallow JSON Schema validator: type, `required`,
    `properties`, `items`, and `enum`. Enough to catch a shape mismatch
    (missing field, wrong type) without taking on a `jsonschema` dependency
    for plumbing that Phases 4/5 will exercise with concrete schemas.
    """
    if not isinstance(schema, dict):
        return

    if "enum" in schema and value not in schema["enum"]:
        raise SchemaValidationError(f"{path}: {value!r} is not one of {schema['enum']}")

    schema_type = schema.get("type")
    if schema_type is not None:
        _validate_type(value, schema_type, path)

    if isinstance(value, dict):
        required = schema.get("required") or []
        missing = [key for key in required if key not in value]
        if missing:
            raise SchemaValidationError(f"{path}: missing required field(s) {missing}")

        properties = schema.get("properties") or {}
        for key, subschema in properties.items():
            if key in value:
                _validate_against_schema(value[key], subschema, f"{path}.{key}")

    elif isinstance(value, list):
        items_schema = schema.get("items")
        if isinstance(items_schema, dict):
            for index, item in enumerate(value):
                _validate_against_schema(item, items_schema, f"{path}[{index}]")


def _response_format_for_rung(rung: int, schema: dict, schema_name: str) -> Optional[dict]:
    if rung == RUNG_JSON_SCHEMA:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": schema,
            },
        }
    if rung == RUNG_JSON_OBJECT:
        return {"type": "json_object"}
    return None


def _messages_for_rung(
    rung: int, messages: List[dict], schema: dict, schema_name: str
) -> List[dict]:
    if rung == RUNG_JSON_SCHEMA:
        # The schema is enforced by the API itself; no need to spell it out
        # in the prompt too.
        return messages
    # Rungs 2 and 3 get no (or only a loose) enforcement from the API, so the
    # schema is inlined as an extra system message instead.
    schema_message = {
        "role": "system",
        "content": (
            f"Respond with ONLY a single JSON object (no prose, no code fence) "
            f"named '{schema_name}' that matches exactly this JSON Schema:\n"
            f"{json.dumps(schema)}"
        ),
    }
    return [schema_message, *messages]


def _is_response_format_rejection(exc: Exception) -> bool:
    """True when the error names `response_format` (or one of its values) as
    the problem -- the signature of a provider rejecting the request *shape*
    outright (Ollama, Anthropic's OpenAI-compat layer, older vLLM, many
    OpenRouter models all 400 this way), as opposed to a schema-validation or
    content failure that stepping down the ladder against the same provider
    can't fix.
    """
    message = str(exc).lower()
    return "response_format" in message or "json_schema" in message or "json_object" in message


def call_structured(
    providers: List[LLMProvider],
    *,
    messages: List[dict],
    schema: dict,
    schema_name: str,
    max_tokens: int,
    timeout: int,
    temperature: float = 0,
) -> Tuple[dict, str]:
    """Call `providers` in order, each through the response-format ladder
    (see module docstring), and return `(payload, model)` — the
    parsed/validated JSON payload and the model string of whichever provider
    produced it.

    For each provider, rungs are tried from that provider's cached
    (or default, strictest) starting rung down to `RUNG_NONE`, stopping at
    the first rung that returns a schema-valid payload. A rung is skipped
    only because a *previous* rung on this same provider failed with a
    `response_format`-shaped rejection; any other failure (schema mismatch,
    refusal, network/auth error) stops the ladder immediately.

    Only once a provider's ladder is exhausted does the loop consider the
    next provider, and even then only when `is_fallback_worthy_error`
    classifies the last failure as quota/auth-related — matching every other
    provider loop in this codebase.

    Raises `StructuredCallError` (or the `SchemaValidationError` subclass) if
    every provider fails, refuses, or returns a response that doesn't
    validate — this call site has no "keep the old result" fallback to fall
    back to, unlike the old `refine_with_llm`.
    """
    if not providers:
        raise StructuredCallError("No LLM provider was supplied to call_structured.")

    last_error: Exception | None = None

    for provider in providers:
        cache_key = _provider_cache_key(provider)
        start_rung = _provider_rung_cache.get(cache_key, RUNG_JSON_SCHEMA)

        provider_error: Exception | None = None

        for rung in _RUNGS:
            if rung < start_rung:
                continue

            response_format = _response_format_for_rung(rung, schema, schema_name)
            rung_messages = _messages_for_rung(rung, messages, schema, schema_name)
            request_kwargs: dict = dict(
                model=provider.model,
                messages=rung_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            if response_format is not None:
                request_kwargs["response_format"] = response_format

            try:
                response = provider.client.chat.completions.create(**request_kwargs)
                choice = response.choices[0]
                refusal = getattr(choice.message, "refusal", None)
                if refusal:
                    raise StructuredCallError(f"LLM refused the request: {refusal}")

                content = choice.message.content or ""
                payload = _parse_json_payload(content)
                _validate_against_schema(payload, schema)

                if rung != start_rung:
                    logger.info(
                        "Structured LLM call '%s' via '%s' provider stepped down "
                        "to rung '%s' (model=%s)",
                        schema_name,
                        provider.label,
                        _RUNG_NAMES[rung],
                        provider.model,
                    )
                _provider_rung_cache[cache_key] = rung

                if provider.label != "primary":
                    logger.info(
                        "Structured LLM call '%s' served by '%s' provider (model=%s)",
                        schema_name,
                        provider.label,
                        provider.model,
                    )
                return payload, provider.model
            except Exception as exc:
                provider_error = exc
                last_error = exc
                logger.warning(
                    "Structured LLM call '%s' via '%s' provider failed at rung '%s': %s: %s",
                    schema_name,
                    provider.label,
                    _RUNG_NAMES[rung],
                    type(exc).__name__,
                    exc,
                )
                if rung < RUNG_NONE and _is_response_format_rejection(exc):
                    # The request *shape* was rejected -- step down and try
                    # again against this same provider before giving up on
                    # it entirely.
                    continue
                # Either this was already the weakest rung, or the failure
                # wasn't about response_format (bad JSON content, schema
                # mismatch, refusal, network/auth error, ...) -- no weaker
                # rung would fix that, so stop this provider's ladder.
                break

        if provider_error is None:
            continue  # unreachable: the loop above always returns or sets this

        if is_fallback_worthy_error(provider_error):
            continue
        # Non-quota/auth error (bad response shape, refusal, validation
        # failure, or a response_format rejection at every rung) — same
        # failure mode as every other provider loop in this codebase: stop
        # here rather than burn the fallback provider on a failure that
        # isn't about quota or auth.
        break

    raise StructuredCallError(
        f"Structured LLM call '{schema_name}' failed on every configured provider"
    ) from last_error
