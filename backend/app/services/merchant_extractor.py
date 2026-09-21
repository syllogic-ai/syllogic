"""
Service for extracting merchant names from transaction descriptions.

Used to populate the merchant field when it's empty but the description
contains identifiable merchant information.
"""

import re
import logging
from typing import Dict, Optional
from dataclasses import dataclass

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class MerchantExtractionResult:
    """Result of merchant extraction."""

    merchant: Optional[str]
    confidence: float  # 0-100
    method: str  # 'alias_table', 'existing', 'known_pattern', 'capitalized_sequence', 'first_word', 'none'
    category_id: Optional[str] = None  # merchant_aliases.category_id, when method == 'alias_table'
    logo_domain: Optional[str] = None  # merchant_aliases.logo_domain, when method == 'alias_table'


@dataclass
class _AliasHint:
    canonical_name: str
    category_id: Optional[str]
    logo_domain: Optional[str]


class MerchantExtractor:
    """
    Extract merchant names from transaction descriptions.

    Usage:
        extractor = MerchantExtractor()
        result = extractor.extract("SEPA INCASSO Netflix BV Amsterdam")
        print(result.merchant)  # "Netflix"
    """

    # Known merchant patterns (brand name -> canonical name)
    # These are common services that appear in various formats
    KNOWN_MERCHANTS = {
        # Streaming Services
        "netflix": "Netflix",
        "spotify": "Spotify",
        "disney": "Disney+",
        "disneyplus": "Disney+",
        "disney+": "Disney+",
        "apple music": "Apple Music",
        "apple tv": "Apple TV+",
        "applemusic": "Apple Music",
        "appletv": "Apple TV+",
        "youtube": "YouTube",
        "youtube premium": "YouTube Premium",
        "hulu": "Hulu",
        "prime video": "Prime Video",
        "primevideo": "Prime Video",
        "hbo": "HBO",
        "hbo max": "HBO Max",
        "paramount": "Paramount+",
        # Cloud & Software
        "aws": "AWS",
        "amazon web services": "AWS",
        "google cloud": "Google Cloud",
        "azure": "Azure",
        "microsoft": "Microsoft",
        "microsoft 365": "Microsoft 365",
        "office 365": "Microsoft 365",
        "github": "GitHub",
        "gitlab": "GitLab",
        "dropbox": "Dropbox",
        "icloud": "iCloud",
        "adobe": "Adobe",
        "figma": "Figma",
        "slack": "Slack",
        "zoom": "Zoom",
        "notion": "Notion",
        "openai": "OpenAI",
        "chatgpt": "OpenAI",
        "anthropic": "Anthropic",
        "vercel": "Vercel",
        "heroku": "Heroku",
        "digitalocean": "DigitalOcean",
        # E-commerce
        "amazon": "Amazon",
        "ebay": "eBay",
        "etsy": "Etsy",
        "aliexpress": "AliExpress",
        "zalando": "Zalando",
        "bol.com": "Bol.com",
        "coolblue": "Coolblue",
        "asos": "ASOS",
        # Transport
        "uber": "Uber",
        "lyft": "Lyft",
        "bolt": "Bolt",
        "lime": "Lime",
        "bird": "Bird",
        "swapfiets": "Swapfiets",
        "ns.nl": "NS",
        "ns ": "NS",
        "ns reizigers": "NS",
        "ns groep": "NS",
        "ov-chipkaart": "OV-chipkaart",
        "ovchipkaart": "OV-chipkaart",
        "translink": "Translink",
        "gvb": "GVB",
        "ret": "RET",
        "htm": "HTM",
        "arriva": "Arriva",
        "connexxion": "Connexxion",
        "ebs": "EBS",
        "flixbus": "FlixBus",
        # Food & Delivery
        "deliveroo": "Deliveroo",
        "uber eats": "Uber Eats",
        "ubereats": "Uber Eats",
        "just eat": "Just Eat",
        "justeat": "Just Eat",
        "thuisbezorgd": "Thuisbezorgd",
        "doordash": "DoorDash",
        "grubhub": "Grubhub",
        "starbucks": "Starbucks",
        "mcdonalds": "McDonald's",
        "mcdonald's": "McDonald's",
        # Utilities & Telecom
        "vattenfall": "Vattenfall",
        "essent": "Essent",
        "eneco": "Eneco",
        "greenchoice": "Greenchoice",
        "ziggo": "Ziggo",
        "kpn": "KPN",
        "t-mobile": "T-Mobile",
        "vodafone": "Vodafone",
        "lebara": "Lebara",
        "odido": "ODIDO",
        "odido netherlands": "ODIDO",
        "odido nederland": "ODIDO",
        # Finance & Insurance
        "paypal": "PayPal",
        "stripe": "Stripe",
        "mollie": "Mollie",
        "revolut": "Revolut",
        "wise": "Wise",
        "transferwise": "Wise",
        "bunq": "Bunq",
        "n26": "N26",
        "zilveren kruis": "Zilveren Kruis",
        "zilverenkruis": "Zilveren Kruis",
        "achmea": "Achmea",
        "centraal beheer": "Centraal Beheer",
        "interpolis": "Interpolis",
        "nationale nederlanden": "Nationale Nederlanden",
        "nn": "Nationale Nederlanden",
        "aegon": "Aegon",
        "asr": "a.s.r.",
        "cz": "CZ",
        "vgz": "VGZ",
        "menzis": "Menzis",
        "ohra": "OHRA",
        "ditzo": "Ditzo",
        "unive": "Univé",
        "abn amro": "ABN AMRO",
        "abnamro": "ABN AMRO",
        "ing": "ING",
        "rabobank": "Rabobank",
        "sns": "SNS",
        "triodos": "Triodos",
        "knab": "Knab",
        # Fitness & Health
        "basic-fit": "Basic-Fit",
        "basicfit": "Basic-Fit",
        "fitfor free": "Fit For Free",
        "anytime fitness": "Anytime Fitness",
        "sportcity": "SportCity",
        "volt45": "VOLT45",
        "volt 45": "VOLT45",
        "trainmore": "TrainMore",
        "sportschool": "Sportschool",
        "fitness": "Fitness",
        "gym": "Gym",
        # Business Services
        "moneybird": "Moneybird",
        "exact": "Exact",
        "xero": "Xero",
        "quickbooks": "QuickBooks",
        "freshbooks": "FreshBooks",
        "mailchimp": "Mailchimp",
        "intercom": "Intercom",
        "sendgrid": "SendGrid",
        "twilio": "Twilio",
    }

    # Noise words to strip from descriptions
    NOISE_PATTERNS = [
        r"\bsepa\b",
        r"\bincasso\b",
        r"\bmachtiging\b",
        r"\bfactnr\b",
        r"\bbtw\b",
        r"\btermijn\b",
        r"\bklantnr\b",
        r"\bcrn\b",
        r"\bnaam\b",
        r"\bomschrijving\b",
        r"\bincassant\b",
        r"\breference\b",
        r"\bref\b",
        r"\bnr\b",
        r"\bnumber\b",
        r"\bpayment\b",
        r"\btransfer\b",
        r"\bid\b",
        r"\bbv\b",  # Dutch company suffix
        r"\bnv\b",  # Dutch company suffix
        r"\bltd\b",
        r"\binc\b",
        r"\bgmbh\b",
        r"\bllc\b",
        r"\bco\b",
        r"\bcorp\b",
    ]

    # Date patterns to strip
    DATE_PATTERNS = [
        r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b",  # DD/MM/YYYY or similar
        r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b",  # YYYY/MM/DD
        r"\b\d{6,8}\b",  # Reference numbers
        r"\b[A-Z]{2,3}\d{10,}\b",  # IBAN-like patterns
    ]

    def __init__(self, db: Optional[Session] = None):
        # Compile regex patterns for performance
        self._noise_pattern = re.compile("|".join(self.NOISE_PATTERNS), re.IGNORECASE)
        self._date_pattern = re.compile("|".join(self.DATE_PATTERNS))
        self.db = db
        self._alias_cache: Optional[Dict[str, _AliasHint]] = None

    def _load_aliases(self) -> Dict[str, _AliasHint]:
        """Load merchant_aliases into memory once per extractor instance."""
        if self._alias_cache is not None:
            return self._alias_cache

        self._alias_cache = {}
        if self.db is None:
            return self._alias_cache

        try:
            from app.models import MerchantAlias

            for row in self.db.query(MerchantAlias).all():
                self._alias_cache[row.pattern.lower()] = _AliasHint(
                    canonical_name=row.canonical_name,
                    category_id=str(row.category_id) if row.category_id else None,
                    logo_domain=row.logo_domain,
                )
        except Exception:
            logger.warning("Failed to load merchant_aliases from database", exc_info=True)

        return self._alias_cache

    def _find_alias(self, text: str) -> Optional[_AliasHint]:
        """Check if text matches a known merchant_aliases pattern (word-boundary match)."""
        aliases = self._load_aliases()
        if not aliases or not text:
            return None

        text_lower = text.lower()
        for pattern, hint in aliases.items():
            if re.search(rf"\b{re.escape(pattern)}\b", text_lower):
                return hint

        return None

    def find_alias_logo_domain(self, text: Optional[str]) -> Optional[str]:
        """Public accessor for callers (e.g. SubscriptionDetector) that only
        need the logo_domain hint for an already-resolved merchant string."""
        hint = self._find_alias(text) if text else None
        return hint.logo_domain if hint else None

    def _clean_description(self, description: str) -> str:
        """
        Remove noise from description to isolate merchant name.

        Args:
            description: Raw transaction description

        Returns:
            Cleaned description string
        """
        if not description:
            return ""

        # Remove date patterns
        cleaned = self._date_pattern.sub(" ", description)

        # Remove noise patterns
        cleaned = self._noise_pattern.sub(" ", cleaned)

        # Remove extra whitespace
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        return cleaned

    # Payment processors - we should look for the actual merchant after these
    PAYMENT_PROCESSORS = {"mollie", "stripe", "paypal", "adyen", "worldpay", "buckaroo"}

    def _find_known_merchant(self, text: str) -> Optional[str]:
        """
        Check if text contains a known merchant name.

        Args:
            text: Text to search

        Returns:
            Canonical merchant name if found, None otherwise
        """
        text_lower = text.lower()

        # First pass: look for specific merchants (not payment processors)
        # This ensures "Mollie VOLT45" matches VOLT45 instead of Mollie
        for pattern, canonical_name in self.KNOWN_MERCHANTS.items():
            # Skip payment processors on first pass
            if pattern.lower() in self.PAYMENT_PROCESSORS:
                continue

            # Check for word boundary matches to avoid false positives
            if re.search(rf"\b{re.escape(pattern)}\b", text_lower):
                return canonical_name

        # Second pass: if no specific merchant found, accept payment processors
        for pattern, canonical_name in self.KNOWN_MERCHANTS.items():
            if pattern.lower() not in self.PAYMENT_PROCESSORS:
                continue

            if re.search(rf"\b{re.escape(pattern)}\b", text_lower):
                return canonical_name

        return None

    def _extract_capitalized_sequence(self, text: str) -> Optional[str]:
        """
        Extract the first capitalized word sequence as potential merchant.

        Args:
            text: Cleaned description text

        Returns:
            Capitalized sequence if found, None otherwise
        """
        if not text:
            return None

        # Find sequences of capitalized words (2+ chars each)
        # This handles "NETFLIX BV" -> "Netflix"
        matches = re.findall(r"\b[A-Z][A-Za-z]{2,}\b", text)

        if matches:
            # Return the first meaningful match
            for match in matches:
                # Skip common noise that slipped through
                if match.lower() not in {
                    "sepa",
                    "incasso",
                    "payment",
                    "transfer",
                    "reference",
                    "naar",
                    "van",
                    "voor",
                    "met",
                    "the",
                    "for",
                    "from",
                    "to",
                }:
                    return match

        # Try finding ALL CAPS sequences
        caps_matches = re.findall(r"\b[A-Z]{3,}\b", text)
        for match in caps_matches:
            if match.lower() not in {"sepa", "iban", "bic", "btw", "kvk", "crn", "ref"}:
                return match.capitalize()

        return None

    def extract(
        self, description: Optional[str], existing_merchant: Optional[str] = None
    ) -> MerchantExtractionResult:
        """
        Extract merchant name from transaction description.

        Priority:
        1. Look up the merchant_aliases table (against existing_merchant if
           present, else description) -- canonicalizes known variants like
           "UBER *EATS8291" -> "Uber Eats" even when a merchant is already set
        2. If existing_merchant is provided and non-empty, return it as-is
        3. Look for known merchant patterns (static KNOWN_MERCHANTS dict)
        4. Extract first capitalized word sequence

        Args:
            description: Transaction description
            existing_merchant: Existing merchant field (will be returned if non-empty)

        Returns:
            MerchantExtractionResult with extracted merchant, confidence, and method
        """
        alias_source = (
            existing_merchant.strip()
            if existing_merchant and existing_merchant.strip()
            else description
        )
        alias_hint = self._find_alias(alias_source) if alias_source else None
        if alias_hint:
            return MerchantExtractionResult(
                merchant=alias_hint.canonical_name,
                confidence=98.0,
                method="alias_table",
                category_id=alias_hint.category_id,
                logo_domain=alias_hint.logo_domain,
            )

        # If merchant already exists, return it
        if existing_merchant and existing_merchant.strip():
            return MerchantExtractionResult(
                merchant=existing_merchant.strip(), confidence=100.0, method="existing"
            )

        if not description:
            return MerchantExtractionResult(merchant=None, confidence=0.0, method="none")

        # 1. Check for known merchant patterns
        known_merchant = self._find_known_merchant(description)
        if known_merchant:
            return MerchantExtractionResult(
                merchant=known_merchant, confidence=95.0, method="known_pattern"
            )

        # 2. Clean description and extract capitalized sequence
        cleaned = self._clean_description(description)
        capitalized = self._extract_capitalized_sequence(cleaned)

        if capitalized:
            # Lower confidence for extracted names (not verified)
            return MerchantExtractionResult(
                merchant=capitalized, confidence=60.0, method="capitalized_sequence"
            )

        # 3. Fallback: use first word if it's meaningful
        words = cleaned.split()
        if words and len(words[0]) >= 3:
            first_word = words[0].capitalize()
            if first_word.lower() not in {
                "the",
                "a",
                "an",
                "to",
                "from",
                "for",
                "at",
                "in",
                "on",
                "by",
            }:
                return MerchantExtractionResult(
                    merchant=first_word, confidence=30.0, method="first_word"
                )

        return MerchantExtractionResult(merchant=None, confidence=0.0, method="none")


def extract_merchant(
    description: Optional[str],
    existing_merchant: Optional[str] = None,
    db: Optional[Session] = None,
) -> Optional[str]:
    """
    Convenience function to extract merchant from description.

    Args:
        description: Transaction description
        existing_merchant: Existing merchant field
        db: Optional DB session -- when provided, canonicalizes against the
            merchant_aliases table (see MerchantExtractor._find_alias)

    Returns:
        Extracted merchant name or None
    """
    extractor = MerchantExtractor(db=db)
    result = extractor.extract(description, existing_merchant)
    return result.merchant


def extract_merchant_full(
    description: Optional[str],
    existing_merchant: Optional[str] = None,
    db: Optional[Session] = None,
) -> MerchantExtractionResult:
    """Same as extract_merchant, but returns the full result (including any
    alias-provided category_id/logo_domain hints) instead of just the name."""
    extractor = MerchantExtractor(db=db)
    return extractor.extract(description, existing_merchant)


def resolve_company_logo_id(db: Optional[Session], domain: Optional[str]):
    """Look up an existing CompanyLogo id by domain.

    Read-only: this backend never creates CompanyLogo rows -- the frontend's
    logo.dev pipeline owns populating that cache. Returns None until the
    frontend has resolved a logo for the domain at least once.
    """
    if not domain or db is None:
        return None

    from app.models import CompanyLogo

    logo = (
        db.query(CompanyLogo)
        .filter(CompanyLogo.domain == domain, CompanyLogo.status == "found")
        .first()
    )
    return logo.id if logo else None
