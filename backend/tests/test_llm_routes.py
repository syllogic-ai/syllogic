from types import SimpleNamespace

from app.routes import llm
from app.services.llm_client import LLMProvider


def _provider(client, model, label):
    return LLMProvider(
        client=client,
        model=model,
        label=label,
        supports_vision=True,
        supports_strict_schema=True,
    )


def test_column_mapping_uses_configured_model(monkeypatch):
    captured = {}

    class StubCompletions:
        @staticmethod
        def create(**kwargs):
            captured.update(kwargs)
            content = """```json
            {"date":"Booked","amount":"Value","description":null,
             "merchant":null,"transactionType":null,"fee":null,"state":null,
             "startingBalance":null,"endingBalance":null,
             "typeConfig":{"isAmountSigned":true,"amountFormat":"DOT_DECIMAL",
             "dateFormat":"YYYY-MM-DD"}}
            ```"""
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=StubCompletions()))
    monkeypatch.setattr(
        llm, "create_llm_clients", lambda db: [_provider(client, "qwen3:8b", "primary")]
    )

    result = llm.map_csv_columns(
        llm.ColumnMappingRequest(
            headers=["Booked", "Value"],
            sample_rows=[["2026-08-17", "-12.50"]],
            date_formats=["YYYY-MM-DD", "DD-MM-YYYY"],
        ),
        db=object(),
    )

    assert captured["model"] == "qwen3:8b"
    assert result["mapping"]["date"] == "Booked"
    assert "2026-08-17" in captured["messages"][0]["content"]


def test_column_mapping_reports_missing_configuration(monkeypatch):
    monkeypatch.setattr(llm, "create_llm_clients", lambda db: [])

    try:
        llm.map_csv_columns(
            llm.ColumnMappingRequest(
                headers=["Date"],
                sample_rows=[],
                date_formats=["DD-MM-YYYY"],
            ),
            db=object(),
        )
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 503
    else:
        raise AssertionError("Expected missing LLM configuration to fail")


def test_column_mapping_falls_back_on_quota_error(monkeypatch):
    captured_models = []

    class QuotaExceeded(Exception):
        pass

    class FailingCompletions:
        @staticmethod
        def create(**kwargs):
            captured_models.append(kwargs["model"])
            raise QuotaExceeded("Error code: 429 - insufficient_quota")

    class FallbackCompletions:
        @staticmethod
        def create(**kwargs):
            captured_models.append(kwargs["model"])
            content = '{"date":"Booked","amount":"Value","description":null,"merchant":null,"transactionType":null,"fee":null,"state":null,"startingBalance":null,"endingBalance":null,"typeConfig":{"isAmountSigned":true,"amountFormat":"DOT_DECIMAL","dateFormat":"YYYY-MM-DD"}}'
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

    primary = SimpleNamespace(chat=SimpleNamespace(completions=FailingCompletions()))
    fallback = SimpleNamespace(chat=SimpleNamespace(completions=FallbackCompletions()))
    monkeypatch.setattr(
        llm,
        "create_llm_clients",
        lambda db: [
            _provider(primary, "gpt-4o-mini", "primary"),
            _provider(fallback, "qwen3:8b", "fallback"),
        ],
    )

    result = llm.map_csv_columns(
        llm.ColumnMappingRequest(
            headers=["Booked", "Value"],
            sample_rows=[["2026-08-17", "-12.50"]],
            date_formats=["YYYY-MM-DD", "DD-MM-YYYY"],
        ),
        db=object(),
    )

    assert captured_models == ["gpt-4o-mini", "qwen3:8b"]
    assert result["mapping"]["date"] == "Booked"
