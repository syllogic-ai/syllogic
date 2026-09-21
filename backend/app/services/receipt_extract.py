"""
Service for turning a scanned receipt image into a structured
`ExtractedReceipt` (header + line items) -- stage 1 of the receipt-ingestion
pipeline. See docs/specs/receipt-ingestion.md Part 1 and
docs/specs/receipt-ingestion-implementation.md 4.0/4.1.

Replaces `receipt_ocr.py` (deleted): that module modelled a receipt as a flat
list of `description, price` pairs recovered by tesseract + a regex. This
module models a receipt as a header (merchant, totals, payment) plus lines
that distinguish gross/discount/net and item/deposit, extracted through a
single vision call under a strict JSON schema -- no OCR step, no regex.

**Rollout flag.** `RECEIPT_EXTRACTION_ENGINE=vision|tesseract` selects the
engine; it defaults to `tesseract` for this release. The vision path is the
fix described in the spec but cannot be exercised against a real provider in
this environment (no API key), so the legacy regex-over-tesseract path is
kept, gated behind the flag, as the rollback plan: flipping one environment
variable reverts to the well-understood (if far less accurate) behaviour
without a code change. The tesseract path deliberately does not carry over
the fixes that only make sense for structured vision output (multi-language
total detection, discount/deposit line splitting) -- it is the old behaviour,
preserved for rollback, not a second implementation of the new one.
"""

from __future__ import annotations

import base64
import io
import logging
import os
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, List, Optional

import pillow_heif
from PIL import Image
from sqlalchemy.orm import Session

from app.services.llm_client import create_llm_clients
from app.services.llm_structured import call_structured

logger = logging.getLogger(__name__)

# iOS "Live Photo" / default camera uploads arrive as HEIC/HEIF, which Pillow
# can't decode without this opener registered. Carried over verbatim from
# receipt_ocr.py -- nothing else in that module survives the rename.
pillow_heif.register_heif_opener()

# Vision endpoints take JPEG/PNG/WebP, not HEIC, and don't need a full-size
# photo -- this is a receipt, not fine art. `normalize_for_vision` always
# transcodes to JPEG so the request builder only ever has one content type to
# reason about, downscaling anything whose long edge exceeds this.
VISION_CONTENT_TYPE = "image/jpeg"
MAX_VISION_LONG_EDGE = 2000
_VISION_JPEG_QUALITY = 90

RECEIPT_EXTRACTION_ENGINE_ENV = "RECEIPT_EXTRACTION_ENGINE"
ENGINE_VISION = "vision"
ENGINE_TESSERACT = "tesseract"
DEFAULT_ENGINE = ENGINE_TESSERACT

_SCHEMA_NAME = "receipt_extraction"

# Spec 1.1, verbatim. `additionalProperties: false` throughout, every field in
# `required` -- nullable where a value may genuinely be absent, so the model
# emits `null` rather than omitting a key or inventing a value.
EXTRACTION_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "merchant",
        "identifiers",
        "booked_at",
        "currency",
        "payment",
        "printed_total",
        "printed_discount_total",
        "lines",
    ],
    "properties": {
        "merchant": {
            "type": "object",
            "additionalProperties": False,
            "required": ["name", "legal_name", "address"],
            "properties": {
                "name": {"type": ["string", "null"]},
                "legal_name": {"type": ["string", "null"]},
                "address": {"type": ["string", "null"]},
            },
        },
        "identifiers": {
            "type": "object",
            "additionalProperties": False,
            "required": ["receipt_no", "fiscal_code", "vat_id"],
            "properties": {
                "receipt_no": {"type": ["string", "null"]},
                "fiscal_code": {"type": ["string", "null"]},
                "vat_id": {"type": ["string", "null"]},
            },
        },
        "booked_at": {"type": ["string", "null"]},
        "currency": {"type": ["string", "null"]},
        "payment": {
            "type": "object",
            "additionalProperties": False,
            "required": ["method", "card_last4"],
            "properties": {
                "method": {
                    "type": ["string", "null"],
                    "enum": ["card", "cash", "other", "unknown", None],
                },
                "card_last4": {"type": ["string", "null"]},
            },
        },
        "printed_total": {"type": ["number", "null"]},
        "printed_discount_total": {"type": ["number", "null"]},
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "id",
                    "raw_text",
                    "name",
                    "quantity",
                    "gross_amount",
                    "discount_amount",
                    "net_amount",
                    "kind",
                    "parent_id",
                ],
                "properties": {
                    "id": {"type": "string"},
                    "raw_text": {"type": ["string", "null"]},
                    "name": {"type": ["string", "null"]},
                    "quantity": {"type": ["number", "null"]},
                    "gross_amount": {"type": ["number", "null"]},
                    "discount_amount": {"type": "number"},
                    "net_amount": {"type": ["number", "null"]},
                    "kind": {"type": "string", "enum": ["item", "deposit"]},
                    "parent_id": {"type": ["string", "null"]},
                },
            },
        },
    },
}

# Transcription-only: the model must not categorize, judge, or total. Each
# rule below maps to a failure seen on a real receipt (spec 1.3).
EXTRACTION_SYSTEM_PROMPT = """You transcribe a photograph of a retail or restaurant receipt into a strict \
JSON object. You do not categorize, judge, or total anything -- you transcribe \
exactly what is printed, in the receipt's original language.

Rules:
- `raw_text` is the verbatim printed line, original language, untouched.
- `name` is `raw_text` with abbreviations expanded (e.g. "Nealk. kokteilis" -> \
"Nealkoholinis kokteilis") -- this is what the line is called, not what it means.
- When a line shows both a list price and a final price (e.g. \
"Nuol. -0,90  Galut. kaina 2,09"): `gross_amount` is the list price, \
`discount_amount` is the reduction as a positive number, `net_amount` is the \
final price actually charged. If there is no discount, `discount_amount` is 0 \
and `gross_amount` equals `net_amount`.
- Packaging deposits (e.g. "Uzstatas", "pant", "pfand", "statins") are their \
own line with `kind` "deposit" and `parent_id` set to the `id` of the item \
line they belong to. A deposit is charged money, not a discount -- never fold \
it into another line's amount.
- A summary block re-listing discounts already shown per line is a recap. Do \
not create line entries from it and do not subtract it again -- use it only to \
fill `printed_discount_total`.
- `printed_total` is the amount actually paid, exactly as printed. Copy it; \
never compute or estimate it, even if it looks like it disagrees with the \
line items.
- If a value is unreadable or absent, emit `null` for it. Never guess a value \
that would make the receipt appear to balance -- an incorrect null is far \
better than a plausible-looking fabrication.
- `id` values are "L1", "L2", ... in the order lines are printed.
- `booked_at` is ISO 8601, using the date and time as printed (local time, no \
timezone conversion).
- `currency` is the ISO 4217 code of the currency actually charged.

Respond with ONLY the JSON object -- no prose, no code fence."""


class ReceiptExtractionError(RuntimeError):
    """Raised when a receipt image can't be turned into an ExtractedReceipt at
    all (unreadable image, engine misconfigured, ...) -- distinct from a
    validation failure, which is a well-formed extraction that doesn't
    reconcile (see receipt_validate.py)."""


@dataclass
class ExtractedLine:
    id: str
    raw_text: Optional[str]
    name: Optional[str]
    quantity: Optional[Decimal]
    gross_amount: Optional[Decimal]
    discount_amount: Decimal
    net_amount: Optional[Decimal]
    kind: str  # "item" | "deposit"
    parent_id: Optional[str]


@dataclass
class ExtractedReceipt:
    merchant_name: Optional[str]
    merchant_legal_name: Optional[str]
    merchant_address: Optional[str]
    receipt_no: Optional[str]
    fiscal_code: Optional[str]
    vat_id: Optional[str]
    booked_at: Optional[str]
    currency: Optional[str]
    payment_method: Optional[str]
    card_last4: Optional[str]
    printed_total: Optional[Decimal]
    printed_discount_total: Optional[Decimal]
    lines: List[ExtractedLine] = field(default_factory=list)
    extraction_model: Optional[str] = None

    @classmethod
    def from_payload(cls, payload: dict, *, model: str) -> "ExtractedReceipt":
        """Builds an `ExtractedReceipt` from the parsed/validated JSON payload
        returned by `call_structured`. Every amount is parsed with
        `Decimal(str(value))`, never `float` -- `Transaction.amount` is
        `Numeric(15, 2)` and validation is exact to the cent (spec 1.2)."""
        merchant = payload.get("merchant") or {}
        identifiers = payload.get("identifiers") or {}
        payment = payload.get("payment") or {}

        lines = [_line_from_payload(raw_line) for raw_line in (payload.get("lines") or [])]

        return cls(
            merchant_name=_clean_str(merchant.get("name")),
            merchant_legal_name=_clean_str(merchant.get("legal_name")),
            merchant_address=_clean_str(merchant.get("address")),
            receipt_no=_clean_str(identifiers.get("receipt_no")),
            fiscal_code=_clean_str(identifiers.get("fiscal_code")),
            vat_id=_clean_str(identifiers.get("vat_id")),
            booked_at=_clean_str(payload.get("booked_at")),
            currency=_clean_str(payload.get("currency")),
            payment_method=_clean_str(payment.get("method")),
            card_last4=_clean_str(payment.get("card_last4")),
            printed_total=_to_decimal(payload.get("printed_total")),
            printed_discount_total=_to_decimal(payload.get("printed_discount_total")),
            lines=lines,
            extraction_model=model,
        )


def _clean_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        # `Decimal(str(value))`, never `Decimal(value)` on a float -- avoids
        # binary-float artifacts like Decimal(2.09) == Decimal('2.0899999...').
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _line_from_payload(raw_line: dict) -> ExtractedLine:
    discount = _to_decimal(raw_line.get("discount_amount"))
    return ExtractedLine(
        id=str(raw_line.get("id") or ""),
        raw_text=_clean_str(raw_line.get("raw_text")),
        name=_clean_str(raw_line.get("name")),
        quantity=_to_decimal(raw_line.get("quantity")),
        gross_amount=_to_decimal(raw_line.get("gross_amount")),
        discount_amount=discount if discount is not None else Decimal("0"),
        net_amount=_to_decimal(raw_line.get("net_amount")),
        kind=_clean_str(raw_line.get("kind")) or "item",
        parent_id=_clean_str(raw_line.get("parent_id")),
    )


def normalize_for_vision(data: bytes, content_type: str) -> tuple[bytes, str]:
    """Transcodes HEIC (and anything else Pillow can open) to JPEG and
    downscales anything whose long edge exceeds `MAX_VISION_LONG_EDGE`.
    Always returns `(bytes, "image/jpeg")` -- the original bytes and content
    type are what gets stored (`receipt_storage.put`); this transcode is only
    ever sent to the vision endpoint (spec 1.4: "store the original, send the
    transcode")."""
    image = Image.open(io.BytesIO(data))
    # HEIC/PNG can carry a palette, alpha channel, or CMYK; JPEG has none of
    # that, and re-encoding a non-RGB image as JPEG raises.
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    elif image.mode == "L":
        image = image.convert("RGB")

    width, height = image.size
    long_edge = max(width, height)
    if long_edge > MAX_VISION_LONG_EDGE:
        scale = MAX_VISION_LONG_EDGE / long_edge
        new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        image = image.resize(new_size, Image.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=_VISION_JPEG_QUALITY)
    return buffer.getvalue(), VISION_CONTENT_TYPE


def _engine() -> str:
    raw = (os.getenv(RECEIPT_EXTRACTION_ENGINE_ENV) or DEFAULT_ENGINE).strip().lower()
    if raw not in (ENGINE_VISION, ENGINE_TESSERACT):
        logger.warning(
            "Unknown %s=%r, falling back to %r",
            RECEIPT_EXTRACTION_ENGINE_ENV,
            raw,
            DEFAULT_ENGINE,
        )
        return DEFAULT_ENGINE
    return raw


def extract_receipt(image: bytes, content_type: str, db: Session) -> ExtractedReceipt:
    """Turns a receipt photo into an `ExtractedReceipt`. Engine selected by
    `RECEIPT_EXTRACTION_ENGINE` (defaults to `tesseract` -- see module
    docstring)."""
    engine = _engine()
    if engine == ENGINE_VISION:
        return _extract_via_vision(image, content_type, db)
    return _extract_via_tesseract(image)


def _extract_via_vision(image: bytes, content_type: str, db: Session) -> ExtractedReceipt:
    normalized, vision_content_type = normalize_for_vision(image, content_type)
    encoded = base64.b64encode(normalized).decode("ascii")
    data_url = f"data:{vision_content_type};base64,{encoded}"

    providers = create_llm_clients(db, requires=frozenset({"vision", "strict_schema"}))
    messages = [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Extract this receipt."},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        },
    ]

    payload, model = call_structured(
        providers,
        messages=messages,
        schema=EXTRACTION_SCHEMA,
        schema_name=_SCHEMA_NAME,
        max_tokens=4000,
        timeout=60,
    )
    return ExtractedReceipt.from_payload(payload, model=model)


# --- Legacy tesseract engine (rollback path) --------------------------------
#
# Everything below is the old receipt_ocr.py regex pass, preserved
# byte-for-byte in spirit (not the exact fixed bugs from spec Part 0 -- see
# module docstring) so RECEIPT_EXTRACTION_ENGINE=tesseract keeps working. It
# is intentionally not the fixed pipeline: no gross/discount/net split, no
# deposit detection, English-only total detection. Every line becomes a
# plain `kind="item"` line with `gross_amount == net_amount` and
# `discount_amount == 0`.

_NON_ITEM_KEYWORDS = (
    "total",
    "subtotal",
    "sub total",
    "tax",
    "vat",
    "change",
    "cash",
    "card",
    "balance",
    "tender",
    "amount due",
)

_ITEM_LINE_RE = re.compile(r"^(?P<description>.+?)\s+[\$€£]?(?P<amount>\d+[.,]\d{2})$")


def _extract_via_tesseract(image: bytes) -> ExtractedReceipt:
    import pytesseract  # local import: only the tesseract engine needs it

    pil_image = Image.open(io.BytesIO(image))
    if pil_image.mode != "L":
        pil_image = pil_image.convert("L")
    raw_text = pytesseract.image_to_string(pil_image)
    return _parse_tesseract_text(raw_text)


def _tesseract_to_decimal(raw: str) -> Optional[Decimal]:
    try:
        return Decimal(raw.replace(",", "."))
    except InvalidOperation:
        return None


def _derive_merchant_name(raw_text: str) -> Optional[str]:
    for line in raw_text.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        if _ITEM_LINE_RE.match(candidate):
            continue
        return candidate
    return None


def _parse_tesseract_text(raw_text: str) -> ExtractedReceipt:
    lines: List[ExtractedLine] = []
    printed_total: Optional[Decimal] = None
    position = 0

    for raw_line in raw_text.splitlines():
        text_line = raw_line.strip()
        if not text_line:
            continue

        match = _ITEM_LINE_RE.match(text_line)
        if not match:
            continue

        amount = _tesseract_to_decimal(match.group("amount"))
        if amount is None:
            continue

        description = match.group("description").strip(" -:\t")
        if not description:
            continue

        if any(keyword in description.lower() for keyword in _NON_ITEM_KEYWORDS):
            if "total" in description.lower() and "sub" not in description.lower():
                printed_total = amount
            continue

        position += 1
        line_id = f"L{position}"
        lines.append(
            ExtractedLine(
                id=line_id,
                raw_text=text_line,
                name=description,
                quantity=None,
                gross_amount=amount,
                discount_amount=Decimal("0"),
                net_amount=amount,
                kind="item",
                parent_id=None,
            )
        )

    return ExtractedReceipt(
        merchant_name=_derive_merchant_name(raw_text),
        merchant_legal_name=None,
        merchant_address=None,
        receipt_no=None,
        fiscal_code=None,
        vat_id=None,
        booked_at=None,
        currency=None,
        payment_method=None,
        card_last4=None,
        printed_total=printed_total,
        printed_discount_total=None,
        lines=lines,
        extraction_model=None,
    )
