"""
Focused tests for localized number parsing and Revolut CSV ingestion.
"""

import os
import sys
import unittest
from decimal import Decimal


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.integrations.number_parsing import infer_amount_format, parse_localized_decimal
from app.integrations.revolut_csv import RevolutCSVAdapter


class NumberParsingTests(unittest.TestCase):
    def test_parse_localized_decimal_variants(self) -> None:
        self.assertEqual(parse_localized_decimal("€ 1.234,56"), Decimal("1234.56"))
        self.assertEqual(parse_localized_decimal("$1,234.56"), Decimal("1234.56"))
        self.assertEqual(parse_localized_decimal("1 234,56"), Decimal("1234.56"))
        self.assertEqual(parse_localized_decimal("123,45-"), Decimal("-123.45"))
        self.assertIsNone(parse_localized_decimal("1,234"))
        self.assertEqual(
            parse_localized_decimal("1,234", allow_grouped_integers_when_ambiguous=True),
            Decimal("1234"),
        )
        self.assertEqual(
            parse_localized_decimal("1,234", amount_format="COMMA_DECIMAL"),
            Decimal("1.234"),
        )

    def test_infer_amount_format(self) -> None:
        self.assertEqual(
            infer_amount_format(["1.234,56", "-12,34", "€ 3.250,00"]),
            "COMMA_DECIMAL",
        )
        self.assertEqual(
            infer_amount_format(["1,234.56", "-12.34", "$3,250.00"]),
            "DOT_DECIMAL",
        )

    def test_revolut_adapter_parses_amount_column_with_comma_decimal(self) -> None:
        csv_content = "\n".join(
            [
                "Type,Product,Completed Date,Description,Amount,Fee,Currency,State",
                "CARD_PAYMENT,Current,02/01/2025 20:48,Grocery Store,\"1.234,56\",\"0,00\",EUR,COMPLETED",
                "CARD_PAYMENT,Current,03/01/2025 09:15,Coffee,\"-12,34\",\"0,00\",EUR,COMPLETED",
            ]
        )

        adapter = RevolutCSVAdapter(csv_content)
        transactions = adapter.fetch_transactions("current")

        self.assertEqual(len(transactions), 2)
        self.assertEqual(transactions[0].amount, Decimal("1234.56"))
        self.assertEqual(transactions[0].transaction_type, "credit")
        self.assertEqual(transactions[1].amount, Decimal("-12.34"))
        self.assertEqual(transactions[1].transaction_type, "debit")

    def test_revolut_adapter_parses_paid_in_paid_out_columns(self) -> None:
        csv_content = "\n".join(
            [
                "Completed Date,Reference,Paid Out (EUR),Paid In (EUR),State",
                "02/01/2025 20:48,Rent,\"1.234,56\",\"0,00\",COMPLETED",
                "03/01/2025 09:15,Salary,\"0,00\",\"2.500,00\",COMPLETED",
            ]
        )

        adapter = RevolutCSVAdapter(csv_content)
        transactions = adapter.fetch_transactions("current")

        self.assertEqual(len(transactions), 2)
        self.assertEqual(transactions[0].amount, Decimal("-1234.56"))
        self.assertEqual(transactions[0].transaction_type, "debit")
        self.assertEqual(transactions[1].amount, Decimal("2500.00"))
        self.assertEqual(transactions[1].transaction_type, "credit")

    def test_revolut_adapter_does_not_coerce_ambiguous_amounts_into_grouped_integers(self) -> None:
        csv_content = "\n".join(
            [
                "Type,Product,Completed Date,Description,Amount,Fee,Currency,State",
                "CARD_PAYMENT,Current,02/01/2025 20:48,Hotel,\"1,234\",0,EUR,COMPLETED",
                "CARD_PAYMENT,Current,03/01/2025 09:15,Salary,\"2,000\",0,EUR,COMPLETED",
            ]
        )

        adapter = RevolutCSVAdapter(csv_content)
        transactions = adapter.fetch_transactions("current")

        self.assertEqual(len(transactions), 0)


if __name__ == "__main__":
    unittest.main()
