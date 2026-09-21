"""Tests for `app.services.receipt_extract` (Phase 4 of the receipt-ingestion
rework). See docs/specs/receipt-ingestion-implementation.md "Phase 4 tests".

The vision provider is mocked throughout -- there is no API key available in
this environment, so nothing here proves a real vision call works. What is
verified: the payload shape sent to `call_structured`, that every amount
comes back as `Decimal` (never `float`), that HEIC is transcoded to JPEG
before being sent, and that the `RECEIPT_EXTRACTION_ENGINE` flag actually
switches engines.
"""

import io
from decimal import Decimal

import pillow_heif
from PIL import Image

from app.services import receipt_extract
from app.services.llm_client import LLMProvider
from app.services.receipt_extract import (
    ExtractedReceipt,
    extract_receipt,
    normalize_for_vision,
)

pillow_heif.register_heif_opener()


def _make_png(size=(200, 100)) -> bytes:
    image = Image.new("RGB", size, color=(255, 0, 0))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _make_heic(size=(3000, 1500)) -> bytes:
    image = Image.new("RGB", size, color=(10, 20, 30))
    heif_file = pillow_heif.from_pillow(image)
    buf = io.BytesIO()
    heif_file.save(buf, format="HEIF")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# normalize_for_vision
# ---------------------------------------------------------------------------


def test_normalize_for_vision_transcodes_heic_to_jpeg():
    heic_bytes = _make_heic(size=(400, 300))
    normalized, content_type = normalize_for_vision(heic_bytes, "image/heic")

    assert content_type == "image/jpeg"
    reopened = Image.open(io.BytesIO(normalized))
    assert reopened.format == "JPEG"


def test_normalize_for_vision_downscales_anything_over_the_long_edge_limit():
    png_bytes = _make_png(size=(5000, 2000))
    normalized, _ = normalize_for_vision(png_bytes, "image/png")

    reopened = Image.open(io.BytesIO(normalized))
    assert max(reopened.size) <= receipt_extract.MAX_VISION_LONG_EDGE


def test_normalize_for_vision_leaves_a_small_image_at_full_size():
    png_bytes = _make_png(size=(200, 100))
    normalized, _ = normalize_for_vision(png_bytes, "image/png")

    reopened = Image.open(io.BytesIO(normalized))
    assert reopened.size == (200, 100)


def test_normalize_for_vision_always_returns_jpeg_content_type():
    png_bytes = _make_png()
    _, content_type = normalize_for_vision(png_bytes, "image/png")
    assert content_type == "image/jpeg"


# ---------------------------------------------------------------------------
# ExtractedReceipt.from_payload -- Decimal, never float
# ---------------------------------------------------------------------------


_SAMPLE_PAYLOAD = {
    "merchant": {"name": "Maxima", "legal_name": "UAB Maxima LT", "address": "Vilniaus g. 1"},
    "identifiers": {"receipt_no": "12345", "fiscal_code": None, "vat_id": "LT100001738313"},
    "booked_at": "2026-08-18T10:00:00",
    "currency": "EUR",
    "payment": {"method": "card", "card_last4": "1234"},
    "printed_total": 4.58,
    "printed_discount_total": 0.9,
    "lines": [
        {
            "id": "L1",
            "raw_text": "Nealk. kokteilis  Nuol. -0,90  Galut. kaina 2,09",
            "name": "Nealkoholinis kokteilis",
            "quantity": 1,
            "gross_amount": 2.99,
            "discount_amount": 0.9,
            "net_amount": 2.09,
            "kind": "item",
            "parent_id": None,
        },
        {
            "id": "L2",
            "raw_text": "Uzstatas",
            "name": "Uzstatas",
            "quantity": 1,
            "gross_amount": 0.5,
            "discount_amount": 0,
            "net_amount": 0.5,
            "kind": "deposit",
            "parent_id": "L1",
        },
        {
            "id": "L3",
            "raw_text": "Duona",
            "name": "Duona",
            "quantity": 1,
            "gross_amount": 1.99,
            "discount_amount": 0,
            "net_amount": 1.99,
            "kind": "item",
            "parent_id": None,
        },
    ],
}


def test_from_payload_parses_every_amount_as_decimal_never_float():
    receipt = ExtractedReceipt.from_payload(_SAMPLE_PAYLOAD, model="gpt-4o-mini")

    assert isinstance(receipt.printed_total, Decimal)
    assert receipt.printed_total == Decimal("4.58")
    assert isinstance(receipt.printed_discount_total, Decimal)
    assert receipt.printed_discount_total == Decimal("0.9")

    for line in receipt.lines:
        assert isinstance(line.discount_amount, Decimal)
        if line.gross_amount is not None:
            assert isinstance(line.gross_amount, Decimal)
        if line.net_amount is not None:
            assert isinstance(line.net_amount, Decimal)
        if line.quantity is not None:
            assert isinstance(line.quantity, Decimal)


def test_from_payload_preserves_header_fields():
    receipt = ExtractedReceipt.from_payload(_SAMPLE_PAYLOAD, model="gpt-4o-mini")

    assert receipt.merchant_name == "Maxima"
    assert receipt.merchant_legal_name == "UAB Maxima LT"
    assert receipt.receipt_no == "12345"
    assert receipt.fiscal_code is None
    assert receipt.vat_id == "LT100001738313"
    assert receipt.currency == "EUR"
    assert receipt.payment_method == "card"
    assert receipt.card_last4 == "1234"
    assert receipt.extraction_model == "gpt-4o-mini"


def test_from_payload_preserves_line_kind_and_parent_id():
    receipt = ExtractedReceipt.from_payload(_SAMPLE_PAYLOAD, model="gpt-4o-mini")
    deposit = next(line for line in receipt.lines if line.kind == "deposit")
    assert deposit.parent_id == "L1"
    assert deposit.id == "L2"


def test_from_payload_defaults_missing_discount_to_zero():
    payload = dict(_SAMPLE_PAYLOAD)
    payload["lines"] = [dict(_SAMPLE_PAYLOAD["lines"][0])]
    payload["lines"][0].pop("discount_amount")
    receipt = ExtractedReceipt.from_payload(payload, model="gpt-4o-mini")
    assert receipt.lines[0].discount_amount == Decimal("0")


def test_from_payload_uses_decimal_str_conversion_to_avoid_float_artifacts():
    # 2.09 as a raw Python float has no exact binary representation; parsing
    # it through Decimal(str(...)) must not leak that imprecision.
    payload = dict(_SAMPLE_PAYLOAD)
    receipt = ExtractedReceipt.from_payload(payload, model="gpt-4o-mini")
    line = receipt.lines[0]
    assert line.net_amount == Decimal("2.09")
    assert str(line.net_amount) == "2.09"


# ---------------------------------------------------------------------------
# extract_receipt -- engine selection, payload sent to call_structured, HEIC
# ---------------------------------------------------------------------------


def test_extract_receipt_defaults_to_tesseract_engine(monkeypatch):
    monkeypatch.delenv(receipt_extract.RECEIPT_EXTRACTION_ENGINE_ENV, raising=False)
    assert receipt_extract._engine() == receipt_extract.ENGINE_TESSERACT


def test_extract_receipt_unknown_engine_value_falls_back_to_default(monkeypatch):
    monkeypatch.setenv(receipt_extract.RECEIPT_EXTRACTION_ENGINE_ENV, "not-a-real-engine")
    assert receipt_extract._engine() == receipt_extract.DEFAULT_ENGINE


def test_extract_receipt_tesseract_engine_does_not_call_the_llm(monkeypatch):
    monkeypatch.setenv(receipt_extract.RECEIPT_EXTRACTION_ENGINE_ENV, "tesseract")
    import sys
    import types

    fake_pytesseract = types.SimpleNamespace(
        image_to_string=lambda *a, **kw: (
            "Milk 2L                3.49\nTotal                   3.49\n"
        )
    )
    monkeypatch.setitem(sys.modules, "pytesseract", fake_pytesseract)

    called = {"llm": False}

    def _fail_if_called(*a, **kw):
        called["llm"] = True
        raise AssertionError("vision path should not be used for the tesseract engine")

    monkeypatch.setattr(receipt_extract, "call_structured", _fail_if_called)

    result = extract_receipt(_make_png(), "image/png", db=object())

    assert called["llm"] is False
    assert result.extraction_model is None
    assert result.printed_total == Decimal("3.49")
    assert len(result.lines) == 1
    assert result.lines[0].name == "Milk 2L"
    assert result.lines[0].kind == "item"
    assert result.lines[0].net_amount == Decimal("3.49")


def test_extract_receipt_vision_engine_calls_call_structured_with_image_and_schema(monkeypatch):
    monkeypatch.setenv(receipt_extract.RECEIPT_EXTRACTION_ENGINE_ENV, "vision")

    fake_provider = LLMProvider(
        client=object(),
        model="gpt-4o-mini",
        label="primary",
        supports_vision=True,
        supports_strict_schema=True,
    )
    monkeypatch.setattr(
        receipt_extract, "create_llm_clients", lambda db, requires=frozenset(): [fake_provider]
    )

    captured = {}

    def _fake_call_structured(
        providers, *, messages, schema, schema_name, max_tokens, timeout, **kw
    ):
        captured["providers"] = providers
        captured["messages"] = messages
        captured["schema"] = schema
        captured["schema_name"] = schema_name
        return _SAMPLE_PAYLOAD, "gpt-4o-mini"

    monkeypatch.setattr(receipt_extract, "call_structured", _fake_call_structured)

    result = extract_receipt(_make_png(), "image/png", db=object())

    assert result.extraction_model == "gpt-4o-mini"
    assert result.printed_total == Decimal("4.58")
    assert captured["schema"] is receipt_extract.EXTRACTION_SCHEMA
    assert captured["providers"] == [fake_provider]

    # The user message must carry an image_url content block -- this is a
    # vision call, not a text call.
    user_message = captured["messages"][-1]
    assert user_message["role"] == "user"
    content_types = {block["type"] for block in user_message["content"]}
    assert "image_url" in content_types
    image_block = next(b for b in user_message["content"] if b["type"] == "image_url")
    assert image_block["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_extract_receipt_vision_engine_sends_the_jpeg_transcode_for_a_heic_upload(monkeypatch):
    monkeypatch.setenv(receipt_extract.RECEIPT_EXTRACTION_ENGINE_ENV, "vision")

    fake_provider = LLMProvider(
        client=object(),
        model="gpt-4o-mini",
        label="primary",
        supports_vision=True,
        supports_strict_schema=True,
    )
    monkeypatch.setattr(
        receipt_extract, "create_llm_clients", lambda db, requires=frozenset(): [fake_provider]
    )

    captured = {}

    def _fake_call_structured(
        providers, *, messages, schema, schema_name, max_tokens, timeout, **kw
    ):
        captured["messages"] = messages
        return _SAMPLE_PAYLOAD, "gpt-4o-mini"

    monkeypatch.setattr(receipt_extract, "call_structured", _fake_call_structured)

    heic_bytes = _make_heic(size=(400, 300))
    extract_receipt(heic_bytes, "image/heic", db=object())

    user_message = captured["messages"][-1]
    image_block = next(b for b in user_message["content"] if b["type"] == "image_url")
    data_url = image_block["image_url"]["url"]
    assert data_url.startswith("data:image/jpeg;base64,")

    # And decoding it back must be a real, openable JPEG -- not just a
    # correctly-labelled content type on the original HEIC bytes.
    import base64 as base64_module

    encoded = data_url.split(",", 1)[1]
    decoded = base64_module.b64decode(encoded)
    reopened = Image.open(io.BytesIO(decoded))
    assert reopened.format == "JPEG"


def test_extract_receipt_vision_engine_requires_vision_and_strict_schema_capability(monkeypatch):
    monkeypatch.setenv(receipt_extract.RECEIPT_EXTRACTION_ENGINE_ENV, "vision")

    captured_requires = {}

    def _fake_create_llm_clients(db, requires=frozenset()):
        captured_requires["requires"] = requires
        return [
            LLMProvider(
                client=object(),
                model="gpt-4o-mini",
                label="primary",
                supports_vision=True,
                supports_strict_schema=True,
            )
        ]

    monkeypatch.setattr(receipt_extract, "create_llm_clients", _fake_create_llm_clients)
    monkeypatch.setattr(
        receipt_extract,
        "call_structured",
        lambda *a, **kw: (_SAMPLE_PAYLOAD, "gpt-4o-mini"),
    )

    extract_receipt(_make_png(), "image/png", db=object())

    assert captured_requires["requires"] == frozenset({"vision", "strict_schema"})
