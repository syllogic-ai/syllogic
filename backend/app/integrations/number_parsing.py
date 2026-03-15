"""
Helpers for parsing localized numeric values from CSV sources.
"""

from decimal import Decimal, InvalidOperation
from typing import Iterable, Literal, Optional
import re


AmountFormat = Literal["AUTO", "DOT_DECIMAL", "COMMA_DECIMAL"]
InferredAmountFormat = Literal["DOT_DECIMAL", "COMMA_DECIMAL", "AMBIGUOUS"]


def infer_amount_format(samples: Iterable[Optional[str]]) -> InferredAmountFormat:
    dot_evidence = 0
    comma_evidence = 0

    for sample in samples:
        parsed = _parse_numeric_token(sample)
        if not parsed:
            continue

        token = parsed["token"]
        dot_count = token.count(".")
        comma_count = token.count(",")

        if dot_count and comma_count:
            if token.rfind(".") > token.rfind(","):
                dot_evidence += 1
            else:
                comma_evidence += 1
            continue

        separator = "." if dot_count else "," if comma_count else None
        if separator is None:
            continue

        digits_after = len(token) - token.rfind(separator) - 1
        if digits_after in (0, 3):
            continue

        if separator == ".":
            dot_evidence += 1
        else:
            comma_evidence += 1

    if dot_evidence > 0 and comma_evidence == 0:
        return "DOT_DECIMAL"
    if comma_evidence > 0 and dot_evidence == 0:
        return "COMMA_DECIMAL"
    return "AMBIGUOUS"


def parse_localized_decimal(
    raw: Optional[str],
    amount_format: AmountFormat = "AUTO",
    inferred_format: InferredAmountFormat = "AMBIGUOUS",
) -> Optional[Decimal]:
    parsed = _parse_numeric_token(raw)
    if not parsed:
        return None

    token = parsed["token"]
    negative = parsed["negative"]
    dot_count = token.count(".")
    comma_count = token.count(",")

    normalized: Optional[str] = None

    if dot_count and comma_count:
        decimal_separator = "." if token.rfind(".") > token.rfind(",") else ","
        normalized = _normalize_with_decimal_separator(token, decimal_separator)
    elif dot_count or comma_count:
        separator = "." if dot_count else ","
        resolved_format = _resolve_amount_format(amount_format, inferred_format)
        if resolved_format:
            decimal_separator = "." if resolved_format == "DOT_DECIMAL" else ","
            normalized = _normalize_with_decimal_separator(token, decimal_separator)
        else:
            digits_after = len(token) - token.rfind(separator) - 1
            if digits_after in (0, 3):
                return None
            normalized = _normalize_with_decimal_separator(token, separator)
    else:
        normalized = token

    if not normalized:
        return None

    try:
        value = Decimal(normalized)
    except InvalidOperation:
        return None

    return -value if negative else value


def _parse_numeric_token(raw: Optional[str]) -> Optional[dict[str, object]]:
    if raw is None:
        return None

    value = (
        str(raw)
        .strip()
        .replace("\u2212", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
    )

    if not value:
        return None

    value = re.sub(r"[^\d.,'’()\-\s\u00A0\u202F]", "", value).strip()
    if not value:
        return None

    negative = False
    if re.fullmatch(r"\(.*\)", value):
        negative = True
        value = value[1:-1]

    if value.startswith("-"):
        negative = True
        value = value[1:]

    if value.endswith("-"):
        negative = True
        value = value[:-1]

    value = re.sub(r"[()'’\s\u00A0\u202F]", "", value).strip()
    if not re.search(r"\d", value):
        return None

    return {"negative": negative, "token": value}


def _resolve_amount_format(
    amount_format: AmountFormat,
    inferred_format: InferredAmountFormat,
) -> Optional[Literal["DOT_DECIMAL", "COMMA_DECIMAL"]]:
    if amount_format != "AUTO":
        return amount_format
    if inferred_format != "AMBIGUOUS":
        return inferred_format
    return None


def _normalize_with_decimal_separator(token: str, decimal_separator: Literal[".", ","]) -> Optional[str]:
    decimal_index = token.rfind(decimal_separator)
    normalized: list[str] = []

    for index, char in enumerate(token):
        if char.isdigit():
            normalized.append(char)
            continue

        if char in (".", ","):
            if char == decimal_separator and index == decimal_index:
                normalized.append(".")
            continue

        return None

    value = "".join(normalized)
    if not value or value == ".":
        return None
    return value
