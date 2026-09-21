import fnmatch
import logging
import os
from dataclasses import dataclass
from typing import FrozenSet, List, Optional

from sqlalchemy.orm import Session

from app.services.app_settings import (
    get_effective_llm_model,
    get_llm_base_url,
    get_llm_fallback_api_key,
    get_llm_fallback_base_url,
    get_llm_fallback_model,
    get_openai_api_key,
)


logger = logging.getLogger(__name__)

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"

# Capability names accepted in `create_llm_clients(..., requires=...)`.
CAPABILITY_VISION = "vision"
CAPABILITY_STRICT_SCHEMA = "strict_schema"

# Known model ids (by glob pattern, matched against the model id with any
# OpenRouter-style vendor segment stripped -- see `_strip_vendor_prefix`)
# that support image input and *some* form of schema-guided JSON output.
# "Strict schema" here does not mean literally OpenAI's
# `response_format={"type": "json_schema", "strict": True}` -- receipt
# extraction's `call_structured` (llm_structured.py) degrades that request
# down a ladder (json_schema -> json_object -> none) per provider, so this
# allowlist only needs to say "this model is worth including in a
# vision/structured-output request", not "this model accepts the strictest
# rung". This is intentionally a prefix/glob allowlist rather than an
# exhaustive match so dated snapshots (e.g. "gpt-4o-2024-08-06") resolve the
# same as their base model. A pattern with no trailing "*" still matches any
# suffix (a plain prefix match), matching the previous behaviour for the
# original OpenAI entries.
_VISION_CAPABLE_MODEL_PREFIXES = (
    "gpt-4o",
    "gpt-4.1",
    "gpt-4-turbo",
    "gpt-5",
    "o1",
    "o3",
    "o4",
    "claude-*",
    "gemini-*",
    "qwen*-vl",
    "llava*",
    "minicpm-v",
    "pixtral*",
    "mistral-small*",
)
_STRICT_SCHEMA_CAPABLE_MODEL_PREFIXES = (
    "gpt-4o",
    "gpt-4.1",
    "gpt-4-turbo",
    "gpt-5",
    "o1",
    "o3",
    "o4",
    "claude-*",
    "gemini-*",
    "qwen*-vl",
    "llava*",
    "minicpm-v",
    "pixtral*",
    "mistral-small*",
)

# OpenRouter (and similar aggregators) prefix a model id with its vendor,
# e.g. "openai/gpt-4o-mini" or "anthropic/claude-3-5-sonnet". Strip that
# segment before matching against the allowlist above so those ids resolve
# the same as the bare model id.
_VENDOR_PREFIXES = ("openai/", "anthropic/", "google/")


def _strip_vendor_prefix(model: str) -> str:
    for vendor in _VENDOR_PREFIXES:
        if model.startswith(vendor):
            return model[len(vendor) :]
    return model


class NoCapableProviderError(RuntimeError):
    """Raised when `requires` filters every configured provider away.

    Unlike an empty provider list (no provider configured at all), this means
    at least one provider exists but none declares the requested
    capabilities — a configuration problem worth surfacing distinctly rather
    than silently returning nothing.
    """


@dataclass(frozen=True)
class LLMProvider:
    """A usable LLM client plus what it's known to support.

    `label` is "primary" or "fallback". Callers loop over providers in order,
    advancing to the next only when `is_fallback_worthy_error` classifies the
    failure as quota/auth-related (see module docstring on that function).
    """

    client: object
    model: str
    label: str
    supports_vision: bool
    supports_strict_schema: bool


def _env_bool(name: str, default: bool = False) -> bool:
    """Same idiom as `backend/celery_app.py`'s `_env_bool`, duplicated here
    rather than imported — importing `celery_app` for a bool parser would
    pull in and instantiate a Celery app as a side effect.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _model_matches_prefix(model: str, prefixes: tuple) -> bool:
    normalized = _strip_vendor_prefix((model or "").strip().lower())
    for pattern in prefixes:
        # A pattern with no "*" is a plain prefix match (the original
        # behaviour); one with a "*" -- e.g. "qwen*-vl" -- is a glob, so a
        # trailing "*" is appended when absent to keep the "matches a dated
        # snapshot too" behaviour for glob patterns as well.
        glob_pattern = pattern if pattern.endswith("*") else f"{pattern}*"
        if fnmatch.fnmatch(normalized, glob_pattern):
            return True
    return False


def _resolve_capability(
    *,
    model: str,
    env_var: str,
    known_model_prefixes: tuple,
    default_when_unset: bool,
) -> bool:
    """Resolution order: explicit env override, then a known-model allowlist,
    then the caller-supplied default (True for primary, False for fallback).
    """
    override = os.getenv(env_var)
    if override is not None:
        return _env_bool(env_var, default=default_when_unset)

    if _model_matches_prefix(model, known_model_prefixes):
        return True

    return default_when_unset


def _primary_capabilities(model: str) -> tuple:
    supports_vision = _resolve_capability(
        model=model,
        env_var="LLM_VISION_CAPABLE",
        known_model_prefixes=_VISION_CAPABLE_MODEL_PREFIXES,
        default_when_unset=True,
    )
    supports_strict_schema = _resolve_capability(
        model=model,
        env_var="LLM_STRICT_SCHEMA_CAPABLE",
        known_model_prefixes=_STRICT_SCHEMA_CAPABLE_MODEL_PREFIXES,
        default_when_unset=True,
    )
    return supports_vision, supports_strict_schema


def _fallback_capabilities(model: str) -> tuple:
    supports_vision = _resolve_capability(
        model=model,
        env_var="LLM_FALLBACK_VISION_CAPABLE",
        known_model_prefixes=_VISION_CAPABLE_MODEL_PREFIXES,
        default_when_unset=False,
    )
    supports_strict_schema = _resolve_capability(
        model=model,
        env_var="LLM_FALLBACK_STRICT_SCHEMA_CAPABLE",
        known_model_prefixes=_STRICT_SCHEMA_CAPABLE_MODEL_PREFIXES,
        default_when_unset=False,
    )
    return supports_vision, supports_strict_schema


def create_llm_client(db: Session) -> Optional[object]:
    """Create a client for OpenAI or an OpenAI-compatible endpoint."""
    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("OpenAI compatibility library is not installed")
        return None

    api_key = get_openai_api_key(db)
    if not api_key:
        return None

    # Always pass an explicit base_url. The openai SDK falls back to reading
    # OPENAI_BASE_URL from the environment directly when base_url isn't
    # passed, and our deployment always sets that variable (possibly to an
    # empty string via `${OPENAI_BASE_URL:-}`), which breaks the SDK's own
    # default-URL fallback.
    base_url = get_llm_base_url() or DEFAULT_OPENAI_BASE_URL
    return OpenAI(api_key=api_key, base_url=base_url)


def create_llm_fallback_client() -> Optional[object]:
    """Create a client for the deployment-configured fallback provider.

    Unlike the primary client, this is env-only (LLM_FALLBACK_BASE_URL /
    LLM_FALLBACK_API_KEY) — there is no per-user database setting for it,
    since it's meant to be a deployment-level safety net (e.g. a local
    Ollama/vLLM server) rather than something end users configure per call.
    """
    base_url = get_llm_fallback_base_url()
    if not base_url:
        return None

    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("OpenAI compatibility library is not installed")
        return None

    return OpenAI(api_key=get_llm_fallback_api_key(), base_url=base_url)


def create_llm_clients(
    db: Session,
    *,
    requires: FrozenSet[str] = frozenset(),
) -> List[LLMProvider]:
    """Return ordered providers: primary first, then fallback.

    Callers should try providers in order, moving to the next one only when
    `is_fallback_worthy_error` classifies the failure as quota/auth-related.

    `requires` filters the result to providers declaring all of the named
    capabilities (`CAPABILITY_VISION`, `CAPABILITY_STRICT_SCHEMA`). Callers
    that pass no `requires` (the default) get exactly the providers they got
    before this parameter existed — this is purely additive for them.

    If `requires` is non-empty and filters every provider away,
    `NoCapableProviderError` is raised rather than returning an empty list —
    an empty list is indistinguishable from "nothing configured", which is a
    different, and differently actionable, problem.
    """
    providers: List[LLMProvider] = []

    primary_client = create_llm_client(db)
    if primary_client is not None:
        primary_model = get_effective_llm_model(db)
        supports_vision, supports_strict_schema = _primary_capabilities(primary_model)
        providers.append(
            LLMProvider(
                client=primary_client,
                model=primary_model,
                label="primary",
                supports_vision=supports_vision,
                supports_strict_schema=supports_strict_schema,
            )
        )

    fallback_client = create_llm_fallback_client()
    if fallback_client is not None:
        fallback_model = get_llm_fallback_model()
        supports_vision, supports_strict_schema = _fallback_capabilities(fallback_model)
        providers.append(
            LLMProvider(
                client=fallback_client,
                model=fallback_model,
                label="fallback",
                supports_vision=supports_vision,
                supports_strict_schema=supports_strict_schema,
            )
        )

    if not requires:
        return providers

    def _is_capable(provider: LLMProvider) -> bool:
        if CAPABILITY_VISION in requires and not provider.supports_vision:
            return False
        if CAPABILITY_STRICT_SCHEMA in requires and not provider.supports_strict_schema:
            return False
        return True

    filtered = [provider for provider in providers if _is_capable(provider)]

    if not filtered:
        raise NoCapableProviderError(
            "No configured LLM provider supports the required capabilities "
            f"({', '.join(sorted(requires))}); none is configured."
        )

    return filtered


def is_fallback_worthy_error(exc: Exception) -> bool:
    """True when the error indicates the primary provider is unusable right
    now (invalid/expired key, exhausted quota, rate limited) rather than a
    transient issue worth retrying against the same provider.
    """
    message = str(exc).lower()
    return (
        "401" in message
        or "authentication" in message
        or "api key" in message
        or "429" in message
        or "rate limit" in message
        or "insufficient_quota" in message
        or "quota" in message
    )
