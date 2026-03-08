"""
OpenAI-powered transformation script generator for bank file imports.

Generates a Python script that:
- Reads the uploaded file (CSV or XLSX)
- Maps source columns to standardised fields
- Filters non-transaction rows
- Normalises dates to ISO 8601
- Extracts balance anchors per day
- Returns a list of structured transaction dicts
"""
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import openai

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert Python developer that writes data transformation scripts for bank file imports.

You will receive column headers and sample data rows from a bank export file.  Your job is to produce a single Python function called `transform(file_path: str) -> list[dict]`.

## Requirements for the transform function

1. **Read the file** using the appropriate parser:
   - For .csv files: use the `csv` module
   - For .xlsx files: use `openpyxl`
   - Detect the file type from the file extension

2. **Map source columns** to these standardised output fields:
   - `date` (str): ISO 8601 date string (YYYY-MM-DD). REQUIRED.
   - `description` (str): Transaction description/narrative. REQUIRED.
   - `amount` (float): Signed amount — negative for debits/expenses, positive for credits/income. REQUIRED.
   - `merchant` (str or None): Merchant/payee name if separate from description.
   - `currency` (str or None): ISO currency code if present.
   - `fee` (float or None): Transaction fee if present.
   - `balance` (float or None): Running/closing balance if present.
   - `transaction_type` (str): "debit" or "credit" based on amount sign.

3. **Combine columns** where needed (e.g. merge separate Amount and Fee columns into a net amount).

4. **Filter out** non-transaction rows (header repetitions, summary rows, blank rows, pending/reverted transactions).

5. **Sort** rows by date ascending.

6. **Balance handling**: If a balance column exists, extract the value for each row. If a row's balance is blank, set it to None (the caller will calculate it).

## Output format

Return a list of dicts, each with the keys above. Example:
```python
[
    {"date": "2025-01-15", "description": "Tesco Groceries", "amount": -42.50, "merchant": "Tesco", "currency": "EUR", "fee": None, "balance": 1234.56, "transaction_type": "debit"},
    ...
]
```

## Constraints

- Only import: `csv`, `openpyxl`, `re`, `datetime`, `json`, `os.path`. NO other imports.
- The function signature must be exactly: `def transform(file_path: str) -> list[dict]:`
- Handle encoding issues gracefully (try utf-8, then latin-1).
- If dates are ambiguous (DD/MM vs MM/DD), prefer DD/MM/YYYY (European) unless the data clearly indicates otherwise.
- For amounts: if the file uses comma as decimal separator, handle it.
- Never call `print()` or `sys.exit()` — just return the list.
- Handle both CSV and XLSX with the same function by checking the file extension.

Respond with ONLY the Python code for the `transform` function (and any helper functions it needs). No markdown fences, no explanation — pure Python only."""


CLARIFICATION_SYSTEM_PROMPT = """You are analysing a bank export file to determine how to parse it.

Given the column headers and sample data, determine if the file structure is clear enough to generate a transformation script, or if you need to ask the user a clarifying question.

If the structure is CLEAR, respond with:
{"status": "clear", "mapping_summary": "...", "transformation_description": "...", "balance_column": "column_name or null"}

If you need CLARIFICATION, respond with:
{"status": "needs_clarification", "question": "Your specific plain-language question"}

The mapping_summary should describe which source column maps to which target field.
The transformation_description should explain any non-obvious logic (e.g. "Amount and Fee columns will be combined into net amount").
Only ask a question if genuinely ambiguous — most bank exports have a clear structure.

Respond ONLY with valid JSON."""


def _get_openai_client() -> openai.OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    return openai.OpenAI(api_key=api_key)


def check_clarity(
    headers: List[str],
    sample_rows: List[List[str]],
    clarification_history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """
    Check whether the file structure is clear enough to generate a script,
    or whether a clarification question is needed.

    Returns a dict with status, mapping_summary, etc.
    """
    client = _get_openai_client()

    sample_data = []
    for row in sample_rows[:5]:
        obj = {}
        for i, h in enumerate(headers):
            obj[h] = row[i] if i < len(row) else ""
        sample_data.append(obj)

    user_msg = (
        f"Column headers: {json.dumps(headers)}\n\n"
        f"Sample data (first rows):\n{json.dumps(sample_data, indent=2)}"
    )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": CLARIFICATION_SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

    if clarification_history:
        for entry in clarification_history:
            messages.append({"role": "assistant", "content": json.dumps(entry.get("question_data", {}))})
            messages.append({"role": "user", "content": entry.get("answer", "")})
        messages.append({"role": "user", "content": "Based on my answer, please re-evaluate."})

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0,
    )

    content = response.choices[0].message.content or ""
    json_match = content.strip()
    if json_match.startswith("```"):
        json_match = json_match.split("```")[1]
        if json_match.startswith("json"):
            json_match = json_match[4:]
        json_match = json_match.strip()

    try:
        return json.loads(json_match)
    except json.JSONDecodeError:
        return {"status": "clear", "mapping_summary": "Auto-detected column mapping", "transformation_description": "", "balance_column": None}


def generate_script(
    headers: List[str],
    sample_rows: List[List[str]],
    clarification_context: Optional[str] = None,
) -> str:
    """
    Generate a Python transformation script using OpenAI.

    Returns the script source code.
    """
    client = _get_openai_client()

    sample_data = []
    for row in sample_rows[:10]:
        obj = {}
        for i, h in enumerate(headers):
            obj[h] = row[i] if i < len(row) else ""
        sample_data.append(obj)

    user_msg = (
        f"Column headers: {json.dumps(headers)}\n\n"
        f"Sample data (first 10 rows):\n{json.dumps(sample_data, indent=2)}"
    )

    if clarification_context:
        user_msg += f"\n\nAdditional context from user:\n{clarification_context}"

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0,
    )

    content = response.choices[0].message.content or ""
    if content.startswith("```"):
        lines = content.split("\n")
        lines = lines[1:]  # remove opening fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines)

    return content.strip()


def generate_script_with_retry(
    headers: List[str],
    sample_rows: List[List[str]],
    file_path: str,
    clarification_context: Optional[str] = None,
    max_retries: int = 3,
) -> Tuple[bool, Optional[str], Optional[List[Dict[str, Any]]], Optional[str]]:
    """
    Generate a script and execute it, retrying up to max_retries on failure.

    Returns (success, script_source, parsed_transactions, error_message).
    """
    from app.services.script_sandbox import execute_script

    last_error = None

    for attempt in range(max_retries):
        logger.info(f"Script generation attempt {attempt + 1}/{max_retries}")

        try:
            if attempt == 0:
                script = generate_script(headers, sample_rows, clarification_context)
            else:
                script = _regenerate_with_error(
                    headers, sample_rows, last_error, clarification_context
                )
        except Exception as e:
            last_error = f"OpenAI API error: {e}"
            logger.error(f"Script generation failed: {last_error}")
            continue

        success, result, error = execute_script(script, file_path)

        if success and result is not None:
            if len(result) == 0:
                last_error = "Script executed successfully but produced zero rows"
                logger.warning(last_error)
                continue

            required = {"date", "description", "amount"}
            first_row_keys = set(result[0].keys()) if result else set()
            missing = required - first_row_keys
            if missing:
                last_error = f"Output missing required fields: {missing}. Got: {first_row_keys}"
                logger.warning(last_error)
                continue

            return True, script, result, None

        last_error = error or "Unknown execution error"
        logger.warning(f"Attempt {attempt + 1} failed: {last_error}")

    return False, None, None, f"All {max_retries} attempts failed. Last error: {last_error}"


def _regenerate_with_error(
    headers: List[str],
    sample_rows: List[List[str]],
    error_message: str,
    clarification_context: Optional[str] = None,
) -> str:
    """Re-generate the script with the previous error as context."""
    client = _get_openai_client()

    sample_data = []
    for row in sample_rows[:10]:
        obj = {}
        for i, h in enumerate(headers):
            obj[h] = row[i] if i < len(row) else ""
        sample_data.append(obj)

    user_msg = (
        f"Column headers: {json.dumps(headers)}\n\n"
        f"Sample data (first 10 rows):\n{json.dumps(sample_data, indent=2)}\n\n"
        f"The previous script FAILED with this error:\n{error_message}\n\n"
        f"Please fix the script to handle this case. Generate a corrected transform function."
    )

    if clarification_context:
        user_msg += f"\n\nAdditional context from user:\n{clarification_context}"

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0,
    )

    content = response.choices[0].message.content or ""
    if content.startswith("```"):
        lines = content.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines)

    return content.strip()
