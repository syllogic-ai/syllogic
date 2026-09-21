"""Lint `categorization_instructions` for references to categories that no
longer exist.

Those strings are free text, edited through `update_category`
(`app/mcp/tools/categories.py`), and they routinely route by name: "anything
from the bakery goes to 'Eating Out', never Groceries". `category_matcher`
feeds them to the model verbatim (`For category 'X': ...`), so once the name
stops resolving -- the category was renamed, merged or deleted -- the
instruction keeps being sent and keeps steering categorization at a target
that is not there. Nothing errors, nothing is logged, and every
categorization that reads the string is quietly a little worse. See
docs/specs/receipt-ingestion-implementation.md 8.1 and
docs/specs/receipt-ingestion.md Part 8.1.

**This module warns; it never fails.** The instructions are prose written by
a human, so false positives are certain, and a hygiene check is not worth a
boot loop or a rejected write. Every public entry point here swallows its
own exceptions and returns an empty result -- a caller can treat "no
findings" and "the lint broke" identically, because in both cases there is
nothing for the user to act on and the write must still go through.

Like `category_tree`, this takes a caller's `Session` rather than opening
its own: both callers (the app lifespan and an MCP write tool) already have
one, and the write path in particular must see its own uncommitted change.
"""

from __future__ import annotations

import logging
import re
from contextlib import closing
from dataclasses import dataclass
from typing import Iterable, Sequence

from sqlalchemy.orm import Session

from app.models import Category

logger = logging.getLogger(__name__)

# How many findings a single startup log line names before it stops. The
# count is always exact; the sample is there to make the line actionable
# without turning a badly-drifted tree into a page of boot output.
MAX_LOGGED_SAMPLES = 10


@dataclass(frozen=True)
class DanglingReference:
    """One name in one category's instructions that does not resolve."""

    category_id: str
    category_name: str
    reference: str
    kind: str  # "quoted" or "title-cased"

    def describe(self) -> str:
        return (
            f"{self.category_name!r} ({self.category_id}) references "
            f"{self.reference!r} ({self.kind}), which is not a category"
        )


# ---------------------------------------------------------------------------
# Candidate extraction
# ---------------------------------------------------------------------------

# Quoting a name is an explicit act, so quoted candidates are taken at face
# value. The two patterns are separate because the single-quote case has to
# survive English: the lookarounds reject an apostrophe that is part of a
# word, so "don't touch it" is not read as an opening quote.
_DOUBLE_QUOTED = re.compile(r"[\"“«`]([^\"“”«»`\n]{1,60})[\"”»`]")
_SINGLE_QUOTED = re.compile(r"(?<![A-Za-z0-9])['‘]([^'‘’\n]{1,60})['’](?![A-Za-z])")

# A title-cased word: initial capital followed by a lowercase letter. The
# second character matters -- it keeps "VAT", "IBAN" and a bare "I" out,
# which are the acronyms and pronouns these instructions are full of.
_TITLE_WORD = r"[A-Z][a-z][A-Za-z'’]*"
_TITLE_RUN = re.compile(
    rf"{_TITLE_WORD}(?:[ \t]+(?:&|and|of|the|for|/)[ \t]+{_TITLE_WORD}|[ \t]+{_TITLE_WORD})*"
)

# Words that, immediately before a capitalised word, mean "what follows is
# where this goes". A single capitalised word on its own is almost always a
# merchant or a place ("anything from Lidl"), so it is only treated as a
# category reference when one of these precedes it.
_ROUTING_CUE = re.compile(
    r"(?:"
    r"categor(?:y|ies|ise|ize|ised|ized)\s+(?:as\s+|to\s+)?"
    r"|go(?:es)?\s+(?:to|in|into|under)\s+"
    r"|belongs?\s+(?:to|in|under)\s+"
    r"|put\s+(?:it\s+|them\s+)?(?:in|under|into)\s+"
    r"|file\s+(?:it\s+|them\s+)?under\s+"
    r"|move\s+(?:it\s+|them\s+)?to\s+"
    r"|route\s+(?:it\s+|them\s+)?to\s+"
    r"|assign\s+(?:it\s+|them\s+)?to\s+"
    r"|classify\s+(?:it\s+|them\s+)?as\s+"
    r"|(?:not|never|prefer|see|under|instead\s+of|rather\s+than)\s+"
    r"|->\s*|→\s*"
    r")$",
    re.IGNORECASE,
)

# Characters that end a sentence (or a bullet's lead-in). A capitalised word
# straight after one of these is capitalised because it starts a sentence,
# not because it names anything.
_SENTENCE_END = set(".!?:;\n\r•-*–—")

_TRAILING_JUNK = re.compile(r"^[\s\"'`‘’“”(\[]+|[\s\"'`‘’“”)\].,;:!?]+$")


def _normalize(name: str) -> str:
    """Fold a name to the form both sides of the comparison are matched on.

    Case, surrounding punctuation, inner whitespace and the `&`/`and`
    spelling are all things a human varies freely when writing prose about a
    category they can see in the UI; none of them is a dangling reference.
    """
    cleaned = _TRAILING_JUNK.sub("", name)
    cleaned = cleaned.replace("&", " and ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip().casefold()
    if cleaned.endswith("'s") or cleaned.endswith("’s"):
        cleaned = cleaned[:-2].strip()
    return cleaned


def _resolves(reference: str, known: set[str]) -> bool:
    """True when `reference` names a category in `known`.

    A reference written as a path ("Food > Groceries", "Food/Groceries")
    resolves on its last segment: the user is naming the leaf and spelling
    out where it lives, which is help, not drift.
    """
    normalized = _normalize(reference)
    if not normalized:
        return True  # nothing to resolve; not a finding
    if normalized in known:
        return True
    for separator in (">", "/", "›"):
        if separator in reference:
            leaf = _normalize(reference.rsplit(separator, 1)[-1])
            if leaf and leaf in known:
                return True
    return False


def _looks_like_a_name(candidate: str) -> bool:
    """Reject quoted spans that are obviously prose rather than a name.

    Quotes get used for emphasis and for whole sentences as often as for
    names. A span with sentence punctuation inside it, or one that runs past
    a handful of words, is the former.
    """
    stripped = _TRAILING_JUNK.sub("", candidate).strip()
    if not stripped or not any(char.isalpha() for char in stripped):
        return False
    if len(stripped) > 60 or len(stripped.split()) > 5:
        return False
    return not any(char in stripped for char in ".!?;:")


def _is_sentence_initial(text: str, start: int) -> bool:
    preceding = text[:start].rstrip(" \t\"'`‘“([")
    if not preceding:
        return True
    return preceding[-1] in _SENTENCE_END


def _title_cased_candidates(text: str) -> Iterable[str]:
    """Title-cased spans worth checking, and only those.

    The heuristic, deliberately conservative -- this is where false
    positives come from, and a warning nobody trusts is a warning nobody
    reads:

    - A run of **two or more** capitalised words is reported wherever it
      appears. Multi-word Title Case is rare in ordinary prose and is
      exactly the shape of a category name ("Home Improvement", "Eating
      Out"). It does still catch multi-word proper nouns ("Amazon Prime"),
      which is the cost this trades for catching real renames.
    - A **single** capitalised word is reported only when a routing cue
      precedes it ("goes to Groceries", "not Dining"). Without a cue, a lone
      capitalised word is overwhelmingly a merchant, a brand or a place
      name, and flagging those would bury the real findings.
    - A capitalised word that starts a sentence is never reported on its
      own: it is capitalised by grammar, not by reference.
    """
    for match in _TITLE_RUN.finditer(text):
        run, start = match.group(0), match.start()
        if _is_sentence_initial(text, start):
            # The first word of a sentence is capitalised by grammar, and a
            # run that starts there has swallowed it ("Never Dining" is one
            # match). Drop that word and judge the rest on its own merits,
            # so the grammar does not lend a real reference a second word it
            # never had.
            tail = re.match(r"\S+[ \t]+", run)
            if not tail:
                continue
            start += tail.end()
            run = run[tail.end() :]
        run = run.strip()
        if not run:
            continue
        if len(run.split()) >= 2 or _ROUTING_CUE.search(text[:start]):
            yield run


def _quoted_candidates(text: str) -> Iterable[str]:
    for pattern in (_DOUBLE_QUOTED, _SINGLE_QUOTED):
        for match in pattern.finditer(text):
            candidate = match.group(1).strip()
            if _looks_like_a_name(candidate):
                yield candidate


# ---------------------------------------------------------------------------
# Linting
# ---------------------------------------------------------------------------


def lint_instructions(
    instructions: str | None,
    known_names: set[str],
    *,
    category_id: str,
    category_name: str,
) -> list[DanglingReference]:
    """Findings for one instruction string against one already-normalized
    set of category names.

    `known_names` is normalized by `_normalize`; callers that build it
    themselves must do the same. Findings are deduplicated on the normalized
    reference, so a name repeated three times in one paragraph is one
    warning, and a quoted hit wins over the title-cased reading of the same
    span.
    """
    if not instructions or not instructions.strip():
        return []

    findings: list[DanglingReference] = []
    seen: set[str] = set()
    own_name = _normalize(category_name)

    for kind, candidates in (
        ("quoted", _quoted_candidates(instructions)),
        ("title-cased", _title_cased_candidates(instructions)),
    ):
        for candidate in candidates:
            normalized = _normalize(candidate)
            if not normalized or normalized in seen or normalized == own_name:
                continue
            if _resolves(candidate, known_names):
                continue
            seen.add(normalized)
            findings.append(
                DanglingReference(
                    category_id=category_id,
                    category_name=category_name,
                    reference=_TRAILING_JUNK.sub("", candidate).strip(),
                    kind=kind,
                )
            )

    return findings


def _known_names(categories: Sequence[Category]) -> set[str]:
    return {_normalize(category.name) for category in categories if category.name}


def lint_user(db: Session, user_id: str) -> list[DanglingReference]:
    """Every dangling reference in one user's instructions.

    Scoped to the user on purpose: category names are per-user, so a name
    that resolves in someone else's tree is still dangling in this one.
    """
    try:
        categories = (
            db.query(Category).filter(Category.user_id == user_id).order_by(Category.name).all()
        )
        known = _known_names(categories)
        findings: list[DanglingReference] = []
        for category in categories:
            findings.extend(
                lint_instructions(
                    category.categorization_instructions,
                    known,
                    category_id=str(category.id),
                    category_name=category.name or "",
                )
            )
        return findings
    except Exception:
        # A hygiene check is never worth taking down the caller. Debug level
        # because the caller (startup, or a write that has already been
        # accepted) has nothing to do about it either.
        logger.debug("category instruction lint failed for user %s", user_id, exc_info=True)
        return []


def lint_category(
    db: Session,
    user_id: str,
    category: Category,
) -> list[DanglingReference]:
    """Findings for a single category, resolved against that user's tree.

    Used by `update_category`, which calls it inside the write's transaction
    so the instructions being linted are the ones just set, not the ones on
    disk.
    """
    try:
        known = _known_names(db.query(Category).filter(Category.user_id == user_id).all())
        return lint_instructions(
            category.categorization_instructions,
            known,
            category_id=str(category.id),
            category_name=category.name or "",
        )
    except Exception:
        logger.debug("category instruction lint failed for a single category", exc_info=True)
        return []


def warning_messages(findings: Iterable[DanglingReference]) -> list[str]:
    """Findings as sentences an agent can hand straight to the user."""
    return [
        f"{finding.reference!r} is referenced in this category's "
        f"categorization_instructions but is not one of your categories "
        f"(matched as {finding.kind}). Rename the reference or ignore this if "
        f"it is not meant as a category."
        for finding in findings
    ]


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------


def log_dangling_references(session_factory) -> None:
    """Log one line naming every user whose instructions have drifted.

    Called from the app lifespan. One query over `categories`, no writes,
    and every failure mode -- an unmigrated database, an unreachable one --
    ends as a debug line rather than a failed boot, for the same reason the
    rest of this module warns instead of raising.
    """
    try:
        with closing(session_factory()) as db:
            categories = db.query(Category).order_by(Category.user_id, Category.name).all()

            by_user: dict[str, list[Category]] = {}
            for category in categories:
                by_user.setdefault(category.user_id, []).append(category)

            findings: list[DanglingReference] = []
            for user_id, user_categories in by_user.items():
                known = _known_names(user_categories)
                for category in user_categories:
                    findings.extend(
                        lint_instructions(
                            category.categorization_instructions,
                            known,
                            category_id=str(category.id),
                            category_name=category.name or "",
                        )
                    )

            if not findings:
                logger.info("Category instruction lint: no dangling references found.")
                return

            sample = "; ".join(f.describe() for f in findings[:MAX_LOGGED_SAMPLES])
            suffix = (
                f" (+{len(findings) - MAX_LOGGED_SAMPLES} more)"
                if len(findings) > MAX_LOGGED_SAMPLES
                else ""
            )
            logger.warning(
                "Category instruction lint: %d categorization_instructions "
                "reference(s) do not resolve against their own tree and are "
                "steering categorization at names that no longer exist: %s%s",
                len(findings),
                sample,
                suffix,
            )
    except Exception:
        logger.debug("Category instruction lint skipped", exc_info=True)
