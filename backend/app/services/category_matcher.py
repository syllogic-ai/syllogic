"""
Service for automatically categorizing transactions based on description/merchant.
Uses deterministic keyword matching first, then falls back to LLM if needed.
"""
import os
import re
import logging
from typing import Optional, List, Dict, Tuple
from sqlalchemy.orm import Session
from decimal import Decimal
from functools import lru_cache
import time
from difflib import SequenceMatcher
from dataclasses import dataclass

from app.models import Category, Transaction

# Configure logger
logger = logging.getLogger(__name__)


@dataclass
class CategoryMatchResult:
    """
    Result of a category matching operation with detailed metadata.

    Attributes:
        category: Matched category (None if no match found)
        method: Method used ('deterministic', 'llm', or 'none')
        confidence_score: Confidence score (0.0-1.0 for deterministic, N/A for LLM)
        tokens_used: Number of tokens used (only for LLM, None otherwise)
        cost_usd: Estimated cost in USD (only for LLM, None otherwise)
        matched_keywords: List of keywords that matched (for deterministic method)
    """
    category: Optional[Category]
    method: str  # 'deterministic', 'llm', 'none'
    confidence_score: Optional[float] = None
    tokens_used: Optional[int] = None
    cost_usd: Optional[float] = None
    matched_keywords: Optional[List[str]] = None


class CategoryMatcher:
    """
    Intelligent transaction categorization service using a two-tier approach.

    This service automatically categorizes financial transactions using:
    1. Deterministic keyword matching (fast, rule-based)
    2. LLM-based categorization (fallback, AI-powered)

    Features:
    - Hierarchical keyword matching with scoring
    - Text normalization for better matching accuracy
    - Configurable LLM fallback with retry logic
    - Category type filtering (income/expense/transfer)
    - Comprehensive logging for debugging

    Environment Variables:
    - OPENAI_API_KEY: OpenAI API key for LLM categorization
    - CATEGORIZATION_LLM_MODEL: LLM model to use (default: gpt-4o-mini)
    - CATEGORIZATION_LLM_TEMPERATURE: Temperature for LLM (default: 0.1)
    - CATEGORIZATION_LLM_MAX_TOKENS: Max tokens for LLM response (default: 50)
    - CATEGORIZATION_LLM_MAX_RETRIES: Number of retries for failed API calls (default: 3)
    - CATEGORIZATION_LLM_RETRY_DELAY: Base delay between retries in seconds (default: 1.0)

    Example:
        >>> matcher = CategoryMatcher(db_session)
        >>> category = matcher.match_category(
        ...     description="TESCO SUPERMARKET",
        ...     merchant="Tesco",
        ...     amount=Decimal("-25.50")
        ... )
        >>> print(category.name)  # "groceries"
    """

    # Deterministic Matching Configuration
    # Set to very high value to deactivate deterministic matching (effectively disabled)
    MIN_CONFIDENCE_THRESHOLD = float(os.getenv("CATEGORIZATION_MIN_CONFIDENCE", "999.0"))  # Minimum % to match

    # LLM Configuration (can be overridden via environment variables)
    LLM_MODEL = os.getenv("CATEGORIZATION_LLM_MODEL", "gpt-4o-mini")
    LLM_TEMPERATURE = float(os.getenv("CATEGORIZATION_LLM_TEMPERATURE", "0.1"))
    LLM_MAX_TOKENS = int(os.getenv("CATEGORIZATION_LLM_MAX_TOKENS", "50"))
    LLM_MAX_RETRIES = int(os.getenv("CATEGORIZATION_LLM_MAX_RETRIES", "3"))
    LLM_RETRY_DELAY = float(os.getenv("CATEGORIZATION_LLM_RETRY_DELAY", "1.0"))

    # OpenAI Pricing (per 1M tokens, as of January 2025)
    # https://openai.com/api/pricing/
    PRICING = {
        "gpt-4o-mini": {"input": 0.150, "output": 0.600},  # per 1M tokens
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4-turbo": {"input": 10.00, "output": 30.00},
        "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    }

    def __init__(
        self, 
        db: Session,
        user_overrides: Optional[List[Dict]] = None,
        additional_instructions: Optional[List[str]] = None
    ):
        """
        Initialize the CategoryMatcher.

        Args:
            db: SQLAlchemy database session for querying categories
            user_overrides: List of transaction overrides with format:
                [{"description": "...", "merchant": "...", "amount": ..., "category_name": "..."}, ...]
            additional_instructions: List of strings with user guidance for categorization
        """
        self.db = db
        self._category_cache: Optional[Dict[str, Category]] = None
        self._keyword_rules: Optional[Dict[str, List[str]]] = None
        self._openai_client = None
        self.user_overrides = user_overrides or []
        self.additional_instructions = additional_instructions or []
    
    def _load_categories(self) -> Dict[str, Category]:
        """
        Load all categories from database into a cache.

        Returns:
            Dictionary mapping category name (lowercase) to Category object
        """
        if self._category_cache is None:
            categories = self.db.query(Category).all()
            if not categories:
                # Return empty dict if no categories exist
                self._category_cache = {}
            else:
                self._category_cache = {cat.name.lower(): cat for cat in categories}
        return self._category_cache
    
    def _get_keyword_rules(self) -> Dict[str, List[str]]:
        """
        Get keyword matching rules for each category.

        Returns:
            Dictionary mapping category name to list of keyword patterns.
            Keywords are matched case-insensitively against normalized transaction text.
        """
        if self._keyword_rules is None:
            self._keyword_rules = {
                # Expenses
                "groceries": [
                    "supermarket", "grocery", "tesco", "sainsbury", "asda", "waitrose",
                    "aldi", "lidl", "co-op", "coop", "morrisons", "food", "market",
                    "spar", "iceland", "m&s food", "marks & spencer food"
                ],
                "transport": [
                    "uber", "lyft", "taxi", "bus", "train", "tube", "metro", "subway",
                    "transport for london", "tfl", "london underground", "national rail",
                    "railway", "station", "parking", "petrol", "gas station", "fuel",
                    "shell", "bp", "esso", "exxon", "chevron", "car rental", "hertz",
                    "avis", "europcar", "zipcar", "lime", "bird", "bolt"
                ],
                "utilities": [
                    "electric", "gas", "water", "utility", "energy", "power", "heating",
                    "internet", "broadband", "wifi", "phone", "mobile", "telecom",
                    "bt", "sky", "virgin", "ee", "vodafone", "o2", "three", "giffgaff"
                ],
                "entertainment": [
                    "netflix", "spotify", "disney", "hulu", "prime video", "cinema",
                    "movie", "theater", "theatre", "concert", "ticket", "event",
                    "cinobo", "youtube premium", "twitch", "gaming", "playstation",
                    "xbox", "nintendo", "steam"
                ],
                "dining out": [
                    "restaurant", "cafe", "coffee", "starbucks", "costa", "nero",
                    "pret", "mcdonald", "kfc", "burger king", "pizza", "pub", "bar",
                    "wetherspoon", "simmons", "pregio", "deliveroo", "ubereats",
                    "just eat", "doordash", "grubhub", "takeaway", "take away"
                ],
                "shopping": [
                    "amazon", "ebay", "etsy", "asos", "zara", "h&m", "primark",
                    "next", "m&s", "john lewis", "debenhams", "argos", "currys",
                    "pc world", "apple store", "nike", "adidas", "retail", "store"
                ],
                "healthcare": [
                    "pharmacy", "pharmacist", "chemist", "boots", "superdrug",
                    "doctor", "dentist", "hospital", "clinic", "medical", "health",
                    "gym", "fitness", "puregym", "virgin active", "nuffield"
                ],
                "subscriptions": [
                    "subscription", "membership", "recurring", "monthly", "annual",
                    "aws", "amazon web services", "openai", "anthropic", "github",
                    "adobe", "microsoft", "office 365", "dropbox", "icloud",
                    "hiwell", "software", "saas"
                ],
                "education": [
                    "university", "college", "school", "tuition", "course", "training",
                    "education", "book", "textbook", "library"
                ],
                "housing": [
                    "rent", "mortgage", "landlord", "property", "real estate",
                    "housing", "accommodation", "hotel", "airbnb", "booking.com"
                ],
                # Income
                "salary": [
                    "salary", "payroll", "wages", "income", "employment"
                ],
                "freelance": [
                    "freelance", "contractor", "consulting", "invoice", "payment received"
                ],
                "investment income": [
                    "dividend", "interest", "investment", "return", "capital gain"
                ],
                # Transfer
                "transfer": [
                    "transfer", "payment from", "payment to", "sent to", "received from"
                ],
            }
        return self._keyword_rules

    def _get_openai_client(self) -> Optional[object]:
        """
        Get or create OpenAI client instance (cached).

        Returns:
            OpenAI client instance if available, None otherwise.
            Returns None if OPENAI_API_KEY is not set or library is not installed.
        """
        if self._openai_client is None:
            try:
                from openai import OpenAI
                api_key = os.getenv("OPENAI_API_KEY")
                if not api_key:
                    logger.warning("OPENAI_API_KEY not set, LLM categorization will be unavailable")
                    return None
                self._openai_client = OpenAI(api_key=api_key)
                logger.info("OpenAI client initialized successfully")
            except ImportError:
                logger.warning("OpenAI library not installed, LLM categorization will be unavailable")
                return None
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {str(e)}")
                return None
        return self._openai_client

    def _check_user_override(
        self,
        description: Optional[str],
        merchant: Optional[str],
        amount: Decimal
    ) -> Optional[Category]:
        """
        Check if there's a user override for this transaction.
        
        Args:
            description: Transaction description
            merchant: Merchant name
            amount: Transaction amount
            
        Returns:
            Category if override found, None otherwise
        """
        if not self.user_overrides:
            return None
        
        normalized_desc = self._normalize_text(description)
        normalized_merchant = self._normalize_text(merchant)
        
        for override in self.user_overrides:
            override_desc = self._normalize_text(override.get("description"))
            override_merchant = self._normalize_text(override.get("merchant"))
            override_amount = override.get("amount")
            override_category = override.get("category_name")
            
            # Match if description and merchant match (case-insensitive, normalized)
            desc_match = (not override_desc or not normalized_desc) or override_desc == normalized_desc
            merchant_match = (not override_merchant or not normalized_merchant) or override_merchant == normalized_merchant
            
            # Don't check for amount match. It's not always accurate.
            amount_match = True # Ignore amount match
            
            if desc_match and merchant_match and amount_match and override_category:
                # Find the category by name
                categories = self._load_categories()
                category = categories.get(override_category.lower())
                if category:
                    logger.info(f"User override matched: '{description}' -> '{category.name}'")
                    return category
        
        return None

    @staticmethod
    def _normalize_text(text: Optional[str]) -> str:
        """
        Normalize text for better matching.
        - Converts to lowercase
        - Removes extra whitespace
        - Removes special characters except spaces and hyphens
        - Removes common prefixes like "payment to", "from"
        """
        if not text:
            return ""

        # Convert to lowercase
        text = text.lower()

        # Remove common transaction prefixes
        prefixes_to_remove = [
            "payment to ", "payment from ", "transfer to ", "transfer from ",
            "sent to ", "received from ", "from ", "to ", "paid to "
        ]
        for prefix in prefixes_to_remove:
            if text.startswith(prefix):
                text = text[len(prefix):]
                break

        # Remove special characters except spaces, hyphens, and ampersands
        text = re.sub(r'[^a-z0-9\s\-&]', ' ', text)

        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        return text

    def _calculate_llm_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """
        Calculate the cost of an LLM API call.

        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            model: Model name

        Returns:
            Cost in USD
        """
        pricing = self.PRICING.get(model, {"input": 0, "output": 0})
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost

    @staticmethod
    def _calculate_similarity(text1: str, text2: str) -> float:
        """
        Calculate similarity ratio between two strings using SequenceMatcher.

        Args:
            text1: First string
            text2: Second string

        Returns:
            Similarity ratio between 0.0 and 1.0 (1.0 = identical)
        """
        if not text1 or not text2:
            return 0.0
        return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()

    def match_category_deterministic(
        self,
        description: Optional[str],
        merchant: Optional[str],
        amount: Decimal,
        transaction_type: Optional[str] = None
    ) -> Optional[Category]:
        """
        Try to match category using deterministic keyword rules.
        
        Args:
            description: Transaction description
            merchant: Merchant name
            amount: Transaction amount (positive for income, negative for expense)
            transaction_type: Transaction type (debit/credit)
            
        Returns:
            Matched Category or None if no match found
        """
        if not description and not merchant:
            return None

        # Normalize and combine description and merchant for matching
        normalized_desc = self._normalize_text(description)
        normalized_merchant = self._normalize_text(merchant)
        search_text = " ".join(filter(None, [normalized_desc, normalized_merchant]))

        # Determine transaction type from amount if not provided
        is_income = amount > 0
        is_transfer = "transfer" in search_text

        logger.debug(f"Matching transaction: '{search_text}' (amount: {amount}, is_income: {is_income})")
        
        # Load categories and rules
        categories = self._load_categories()
        rules = self._get_keyword_rules()
        
        # Check for transfer first (highest priority)
        if is_transfer:
            transfer_cat = categories.get("transfer")
            if transfer_cat:
                logger.info(f"Matched transfer transaction to category '{transfer_cat.name}'")
                return transfer_cat
        
        # Match against keyword rules using exact matching only
        best_match = None
        best_confidence = 0.0
        matched_keywords = []

        for category_name, keywords in rules.items():
            category = categories.get(category_name)
            if not category:
                continue

            # Skip if category type doesn't match transaction type
            if is_income and category.category_type != "income":
                continue
            if not is_income and not is_transfer and category.category_type == "income":
                continue

            # Count exact keyword matches
            category_matched_keywords = []
            for keyword in keywords:
                if keyword in search_text:
                    category_matched_keywords.append(keyword)

            # Match if at least one keyword matches exactly
            # Confidence = percentage of keywords matched (min 1 match = some confidence)
            if category_matched_keywords:
                confidence = (len(category_matched_keywords) / len(keywords)) * 100.0
                # Ensure minimum confidence of 10% if at least one keyword matched
                confidence = max(confidence, 10.0)
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = category
                    matched_keywords = category_matched_keywords

        # Return if we have at least one keyword match AND confidence meets threshold
        if best_match and matched_keywords and best_confidence >= self.MIN_CONFIDENCE_THRESHOLD:
            logger.info(
                f"Matched transaction to category '{best_match.name}' "
                f"with confidence {best_confidence:.1f}% (keywords: {', '.join(matched_keywords[:3])})"
            )
            return best_match

        if best_match and matched_keywords:
            logger.debug(
                f"Deterministic match found but confidence {best_confidence:.1f}% "
                f"below threshold {self.MIN_CONFIDENCE_THRESHOLD}%"
            )

        logger.debug(f"No deterministic match found for transaction: '{search_text}'")
        return None
    
    def match_category_llm(
        self,
        description: Optional[str],
        merchant: Optional[str],
        amount: Decimal,
        available_categories: List[Category]
    ) -> Optional[Category]:
        """
        Use LLM to suggest a category when deterministic matching fails.

        Args:
            description: Transaction description
            merchant: Merchant name
            amount: Transaction amount
            available_categories: List of available categories to choose from

        Returns:
            Suggested Category or None if LLM call fails
        """
        # Get OpenAI client (returns None if not available)
        client = self._get_openai_client()
        if not client:
            return None

        # Determine transaction type
        is_income = amount > 0
        transaction_type_str = "income" if is_income else "expense"

        # Filter categories by type
        relevant_categories = [
            cat for cat in available_categories
            if cat.category_type == transaction_type_str or cat.category_type == "transfer"
        ]

        if not relevant_categories:
            logger.warning(f"No relevant categories found for {transaction_type_str} transaction")
            return None

        # Build category list for prompt
        category_list = "\n".join([f"- {cat.name}" for cat in relevant_categories])

        # Build enhanced prompt with additional instructions and user overrides
        instructions_text = ""
        if self.additional_instructions:
            instructions_text = "\n\nUser-specific categorization guidelines:\n" + "\n".join([f"- {inst}" for inst in self.additional_instructions]) + "\n"
        
        overrides_text = ""
        if self.user_overrides:
            overrides_text = "\n\nUser-defined category overrides (use these patterns as examples):\n"
            for override in self.user_overrides:
                desc = override.get("description", "N/A")
                merch = override.get("merchant", "N/A")
                cat = override.get("category_name", "N/A")
                overrides_text += f"- Description: '{desc}', Merchant: '{merch}' → Category: '{cat}'\n"
            overrides_text += "\n"
        
        # Build enhanced prompt
        prompt = f"""Categorize this financial transaction by selecting the most appropriate category.

Transaction details:
- Description: {description or 'N/A'}
- Merchant: {merchant or 'N/A'}
- Amount: {abs(amount)} {transaction_type_str.upper()}
- Type: {transaction_type_str}

Available categories:
{category_list}
{overrides_text}{instructions_text}
Instructions:
1. Analyze the transaction description and merchant name
2. Select the MOST SPECIFIC category that matches
3. Follow any user-specific guidelines and override patterns provided above
4. If the transaction matches a user override pattern, use that category
5. Respond with ONLY the exact category name from the list
6. If no category fits well, respond with "UNKNOWN"

Category name:"""

        # Retry logic for API calls
        last_error = None
        for attempt in range(self.LLM_MAX_RETRIES):
            try:
                logger.debug(f"LLM categorization attempt {attempt + 1}/{self.LLM_MAX_RETRIES}")

                response = client.chat.completions.create(
                    model=self.LLM_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a financial transaction categorization expert. Always respond with only the category name, nothing else."
                        },
                        {"role": "user", "content": prompt}
                    ],
                    temperature=self.LLM_TEMPERATURE,
                    max_tokens=self.LLM_MAX_TOKENS
                )

                suggested_name = response.choices[0].message.content.strip()
                logger.debug(f"LLM suggested category: '{suggested_name}'")

                # Handle UNKNOWN response
                if suggested_name.upper() == "UNKNOWN":
                    logger.info("LLM could not confidently categorize transaction")
                    return None

                # Find matching category (case-insensitive)
                for cat in relevant_categories:
                    if cat.name.lower() == suggested_name.lower():
                        logger.info(f"LLM matched transaction to category '{cat.name}'")
                        return cat

                logger.warning(f"LLM suggested '{suggested_name}' but it doesn't match any available category")
                return None

            except Exception as e:
                last_error = e
                error_type = type(e).__name__
                error_msg = str(e)
                logger.warning(f"LLM categorization attempt {attempt + 1} failed: {error_type}: {error_msg}")

                # Provide diagnostics for common error types
                error_lower = error_msg.lower()
                if "401" in error_msg or "authentication" in error_lower or "api key" in error_lower:
                    logger.error(f"[LLM] DIAGNOSIS: Authentication error - API key may be invalid or expired")
                elif "429" in error_msg or "rate limit" in error_lower:
                    logger.error(f"[LLM] DIAGNOSIS: Rate limit exceeded - wait before retrying")
                elif "timeout" in error_lower:
                    logger.error(f"[LLM] DIAGNOSIS: Request timeout")
                elif "network" in error_lower or "connection" in error_lower:
                    logger.error(f"[LLM] DIAGNOSIS: Network connectivity issue")

                if attempt < self.LLM_MAX_RETRIES - 1:
                    delay = self.LLM_RETRY_DELAY * (attempt + 1)
                    logger.debug(f"[LLM] Retrying in {delay} seconds...")
                    time.sleep(delay)  # Exponential backoff
                    continue
                else:
                    logger.error(f"LLM categorization failed after {self.LLM_MAX_RETRIES} attempts: {error_type}: {error_msg}")
                    import traceback
                    logger.debug(f"[LLM] Final error traceback:\n{traceback.format_exc()}")
                    return None

        return None

    def _match_category_llm_with_details(
        self,
        description: Optional[str],
        merchant: Optional[str],
        amount: Decimal,
        available_categories: List[Category]
    ) -> Tuple[Optional[Category], int, float]:
        """
        Use LLM to suggest a category with detailed token usage information.

        Args:
            description: Transaction description
            merchant: Merchant name
            amount: Transaction amount
            available_categories: List of available categories to choose from

        Returns:
            Tuple of (Category or None, total_tokens_used, cost_in_usd)
        """
        # Get OpenAI client (returns None if not available)
        client = self._get_openai_client()
        if not client:
            return None, 0, 0.0

        # Determine transaction type
        is_income = amount > 0
        transaction_type_str = "income" if is_income else "expense"

        # Filter categories by type
        relevant_categories = [
            cat for cat in available_categories
            if cat.category_type == transaction_type_str or cat.category_type == "transfer"
        ]

        if not relevant_categories:
            logger.warning(f"No relevant categories found for {transaction_type_str} transaction")
            return None, 0, 0.0

        # Build category list for prompt
        category_list = "\n".join([f"- {cat.name}" for cat in relevant_categories])

        # Build enhanced prompt with additional instructions and user overrides
        instructions_text = ""
        if self.additional_instructions:
            instructions_text = "\n\nUser-specific categorization guidelines:\n" + "\n".join([f"- {inst}" for inst in self.additional_instructions]) + "\n"
        
        overrides_text = ""
        if self.user_overrides:
            overrides_text = "\n\nUser-defined category overrides (use these patterns as examples):\n"
            for override in self.user_overrides:
                desc = override.get("description", "N/A")
                merch = override.get("merchant", "N/A")
                cat = override.get("category_name", "N/A")
                overrides_text += f"- Description: '{desc}', Merchant: '{merch}' → Category: '{cat}'\n"
            overrides_text += "\n"
        
        # Build enhanced prompt
        prompt = f"""Categorize this financial transaction by selecting the most appropriate category.

Transaction details:
- Description: {description or 'N/A'}
- Merchant: {merchant or 'N/A'}
- Amount: {abs(amount)} {transaction_type_str.upper()}
- Type: {transaction_type_str}

Available categories:
{category_list}
{overrides_text}{instructions_text}
Instructions:
1. Analyze the transaction description and merchant name
2. Select the MOST SPECIFIC category that matches
3. Follow any user-specific guidelines and override patterns provided above
4. If the transaction matches a user override pattern, use that category
5. Respond with ONLY the exact category name from the list
6. If no category fits well, respond with "UNKNOWN"

Category name:"""

        # Retry logic for API calls
        last_error = None
        for attempt in range(self.LLM_MAX_RETRIES):
            try:
                logger.debug(f"LLM categorization attempt {attempt + 1}/{self.LLM_MAX_RETRIES}")

                response = client.chat.completions.create(
                    model=self.LLM_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a financial transaction categorization expert. Always respond with only the category name, nothing else."
                        },
                        {"role": "user", "content": prompt}
                    ],
                    temperature=self.LLM_TEMPERATURE,
                    max_tokens=self.LLM_MAX_TOKENS
                )

                # Extract token usage
                input_tokens = response.usage.prompt_tokens
                output_tokens = response.usage.completion_tokens
                total_tokens = response.usage.total_tokens

                # Calculate cost
                cost = self._calculate_llm_cost(input_tokens, output_tokens, self.LLM_MODEL)

                suggested_name = response.choices[0].message.content.strip()
                logger.debug(
                    f"LLM suggested category: '{suggested_name}' "
                    f"(tokens: {total_tokens}, cost: ${cost:.6f})"
                )

                # Handle UNKNOWN response
                if suggested_name.upper() == "UNKNOWN":
                    logger.info("LLM could not confidently categorize transaction")
                    return None, total_tokens, cost

                # Find matching category (case-insensitive)
                for cat in relevant_categories:
                    if cat.name.lower() == suggested_name.lower():
                        logger.info(
                            f"LLM matched transaction to category '{cat.name}' "
                            f"(tokens: {total_tokens}, cost: ${cost:.6f})"
                        )
                        return cat, total_tokens, cost

                logger.warning(f"LLM suggested '{suggested_name}' but it doesn't match any available category")
                return None, total_tokens, cost

            except Exception as e:
                last_error = e
                error_type = type(e).__name__
                error_msg = str(e)
                logger.warning(f"LLM categorization attempt {attempt + 1} failed: {error_type}: {error_msg}")

                # Provide diagnostics for common error types
                error_lower = error_msg.lower()
                if "401" in error_msg or "authentication" in error_lower or "api key" in error_lower:
                    logger.error(f"[LLM] DIAGNOSIS: Authentication error - API key may be invalid or expired")
                elif "429" in error_msg or "rate limit" in error_lower:
                    logger.error(f"[LLM] DIAGNOSIS: Rate limit exceeded - wait before retrying")
                elif "timeout" in error_lower:
                    logger.error(f"[LLM] DIAGNOSIS: Request timeout")
                elif "network" in error_lower or "connection" in error_lower:
                    logger.error(f"[LLM] DIAGNOSIS: Network connectivity issue")

                if attempt < self.LLM_MAX_RETRIES - 1:
                    delay = self.LLM_RETRY_DELAY * (attempt + 1)
                    logger.debug(f"[LLM] Retrying in {delay} seconds...")
                    time.sleep(delay)  # Exponential backoff
                    continue
                else:
                    logger.error(f"LLM categorization failed after {self.LLM_MAX_RETRIES} attempts: {error_type}: {error_msg}")
                    import traceback
                    logger.debug(f"[LLM] Final error traceback:\n{traceback.format_exc()}")
                    return None, 0, 0.0

        return None, 0, 0.0

    def match_category(
        self,
        description: Optional[str],
        merchant: Optional[str],
        amount: Decimal,
        transaction_type: Optional[str] = None,
        use_llm: bool = True
    ) -> Optional[Category]:
        """
        Match a transaction to a category.
        Checks user overrides first, then tries deterministic matching, then LLM if enabled.
        
        Args:
            description: Transaction description
            merchant: Merchant name
            amount: Transaction amount
            transaction_type: Transaction type (debit/credit)
            use_llm: Whether to use LLM fallback if deterministic matching fails
            
        Returns:
            Matched Category or None
        """
        # Check user overrides first (highest priority)
        override_category = self._check_user_override(description, merchant, amount)
        if override_category:
            return override_category
        
        # Try deterministic matching
        category = self.match_category_deterministic(
            description=description,
            merchant=merchant,
            amount=amount,
            transaction_type=transaction_type
        )
        
        if category:
            return category
        
        # Fall back to LLM if enabled
        if use_llm:
            categories = list(self._load_categories().values())
            category = self.match_category_llm(
                description=description,
                merchant=merchant,
                amount=amount,
                available_categories=categories
            )
            if category:
                return category

        return None

    def match_category_with_details(
        self,
        description: Optional[str],
        merchant: Optional[str],
        amount: Decimal,
        transaction_type: Optional[str] = None,
        use_llm: bool = True
    ) -> CategoryMatchResult:
        """
        Match a transaction to a category with detailed metadata.
        Returns information about which method was used, token usage, and costs.

        Args:
            description: Transaction description
            merchant: Merchant name
            amount: Transaction amount
            transaction_type: Transaction type (debit/credit)
            use_llm: Whether to use LLM fallback if deterministic matching fails

        Returns:
            CategoryMatchResult with detailed information about the matching process
        """
        # Try deterministic matching first
        if not description and not merchant:
            return CategoryMatchResult(
                category=None,
                method="none",
                confidence_score=0.0
            )

        # Check user overrides first (highest priority)
        override_category = self._check_user_override(description, merchant, amount)
        if override_category:
            logger.info(f"User override matched transaction to category '{override_category.name}'")
            return CategoryMatchResult(
                category=override_category,
                method="override",
                confidence_score=100.0,
                matched_keywords=["user_override"]
            )
        
        # Normalize and combine description and merchant for matching
        normalized_desc = self._normalize_text(description)
        normalized_merchant = self._normalize_text(merchant)
        search_text = " ".join(filter(None, [normalized_desc, normalized_merchant]))

        # Determine transaction type from amount if not provided
        is_income = amount > 0
        is_transfer = "transfer" in search_text

        logger.debug(f"Matching transaction with details: '{search_text}' (amount: {amount}, is_income: {is_income})")

        # Load categories and rules
        categories = self._load_categories()
        rules = self._get_keyword_rules()

        # Check for transfer first (highest priority)
        if is_transfer:
            transfer_cat = categories.get("transfer")
            if transfer_cat:
                logger.info(f"Matched transfer transaction to category '{transfer_cat.name}'")
                return CategoryMatchResult(
                    category=transfer_cat,
                    method="deterministic",
                    confidence_score=100.0,
                    matched_keywords=["transfer"]
                )

        # Match against keyword rules using exact matching only
        best_match = None
        best_confidence = 0.0
        matched_keywords = []

        for category_name, keywords in rules.items():
            category = categories.get(category_name)
            if not category:
                continue

            # Skip if category type doesn't match transaction type
            if is_income and category.category_type != "income":
                continue
            if not is_income and not is_transfer and category.category_type == "income":
                continue

            # Count exact keyword matches
            category_matched_keywords = []
            for keyword in keywords:
                if keyword in search_text:
                    category_matched_keywords.append(keyword)

            # Match if at least one keyword matches exactly
            # Confidence = percentage of keywords matched (min 1 match = some confidence)
            if category_matched_keywords:
                confidence = (len(category_matched_keywords) / len(keywords)) * 100.0
                # Ensure minimum confidence of 10% if at least one keyword matched
                confidence = max(confidence, 10.0)
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = category
                    matched_keywords = category_matched_keywords

        # Return if we have at least one keyword match AND confidence meets threshold
        if best_match and matched_keywords and best_confidence >= self.MIN_CONFIDENCE_THRESHOLD:
            logger.info(
                f"Matched transaction to category '{best_match.name}' "
                f"with confidence {best_confidence:.1f}% (keywords: {', '.join(matched_keywords[:3])})"
            )
            return CategoryMatchResult(
                category=best_match,
                method="deterministic",
                confidence_score=best_confidence,
                matched_keywords=matched_keywords
            )

        if best_match and matched_keywords:
            logger.debug(
                f"Deterministic match found but confidence {best_confidence:.1f}% "
                f"below threshold {self.MIN_CONFIDENCE_THRESHOLD}%"
            )

        logger.debug(f"No deterministic match found for transaction: '{search_text}'")

        # Fall back to LLM if enabled
        if use_llm:
            all_categories = list(categories.values())
            category, tokens, cost = self._match_category_llm_with_details(
                description=description,
                merchant=merchant,
                amount=amount,
                available_categories=all_categories
            )

            if category:
                return CategoryMatchResult(
                    category=category,
                    method="llm",
                    tokens_used=tokens,
                    cost_usd=cost
                )
            elif tokens > 0:
                # LLM was called but couldn't categorize
                return CategoryMatchResult(
                    category=None,
                    method="llm",
                    tokens_used=tokens,
                    cost_usd=cost
                )

        # No match found
        return CategoryMatchResult(
            category=None,
            method="none",
            confidence_score=0.0
        )

    def match_categories_batch_llm(
        self,
        transactions: List[Dict],
        max_batch_size: int = 50
    ) -> Tuple[Dict[int, Tuple[Category, float]], int, float]:
        """
        Batch categorize multiple transactions in a single LLM call.

        Args:
            transactions: List of dicts with keys: index, description, merchant, amount
            max_batch_size: Maximum transactions per API call (to fit context window)

        Returns:
            Tuple of (dict mapping index to (Category, confidence), total_tokens, total_cost)
        """
        logger.info(f"[BATCH LLM] Starting batch categorization for {len(transactions)} transactions")

        client = self._get_openai_client()
        if not client:
            logger.warning("[BATCH LLM] OpenAI client not available")
            return {}, 0, 0.0

        if not transactions:
            logger.info("[BATCH LLM] No transactions to process")
            return {}, 0, 0.0

        categories = self._load_categories()
        logger.info(f"[BATCH LLM] Loaded {len(categories)} categories from database")
        all_categories = list(categories.values())

        # Separate expense and income categories
        expense_categories = [c for c in all_categories if c.category_type in ("expense", "transfer")]
        income_categories = [c for c in all_categories if c.category_type in ("income", "transfer")]

        expense_list = "\n".join([f"- {c.name}" for c in expense_categories])
        income_list = "\n".join([f"- {c.name}" for c in income_categories])

        # Check user overrides first and filter them out from LLM batch
        override_results = {}
        llm_transactions = []
        
        for txn in transactions:
            idx = txn["index"]
            override_category = self._check_user_override(
                txn.get("description"),
                txn.get("merchant"),
                Decimal(str(txn["amount"]))
            )
            if override_category:
                override_results[idx] = (override_category, 100.0)  # 100% confidence for overrides
                logger.debug(f"User override matched transaction {idx} to '{override_category.name}'")
            else:
                llm_transactions.append(txn)
        
        if not llm_transactions:
            logger.info(f"[BATCH LLM] All transactions matched via user overrides")
            return override_results, 0, 0.0

        results = override_results.copy()  # Start with override results
        total_tokens = 0
        total_cost = 0.0

        # Process remaining transactions (not matched by overrides) in batches
        for batch_start in range(0, len(llm_transactions), max_batch_size):
            batch = llm_transactions[batch_start:batch_start + max_batch_size]
            logger.info(f"[BATCH LLM] Processing batch {batch_start // max_batch_size + 1}, size: {len(batch)}")

            # Build transaction list for prompt
            txn_lines = []
            for txn in batch:
                txn_type = "INCOME" if txn["amount"] > 0 else "EXPENSE"
                txn_lines.append(
                    f"{txn['index']}|{txn.get('description', 'N/A')}|{txn.get('merchant', 'N/A')}|{abs(txn['amount'])}|{txn_type}"
                )

            transactions_text = "\n".join(txn_lines)
            logger.debug(f"[BATCH LLM] Transactions text:\n{transactions_text}")

            # Build instructions text if provided
            instructions_text = ""
            if self.additional_instructions:
                instructions_text = "\n\nUser-specific categorization guidelines:\n" + "\n".join([f"- {inst}" for inst in self.additional_instructions]) + "\n"
            
            overrides_text = ""
            if self.user_overrides:
                overrides_text = "\n\nUser-defined category overrides (use these patterns as examples):\n"
                for override in self.user_overrides:
                    desc = override.get("description", "N/A")
                    merch = override.get("merchant", "N/A")
                    cat = override.get("category_name", "N/A")
                    overrides_text += f"- Description: '{desc}', Merchant: '{merch}' → Category: '{cat}'\n"
                overrides_text += "\n"
            
            prompt = f"""Categorize each financial transaction below. Each line is: INDEX|DESCRIPTION|MERCHANT|AMOUNT|TYPE

Transactions:
{transactions_text}

Available categories for EXPENSE transactions:
{expense_list}

Available categories for INCOME transactions:
{income_list}
{overrides_text}{instructions_text}
Instructions:
1. For each transaction, select the most appropriate category from the list matching its TYPE
2. Follow any user-specific guidelines and override patterns provided above
3. If a transaction matches a user override pattern, use that category
4. Respond with one line per transaction in format: INDEX|CATEGORY_NAME|CONFIDENCE
5. CONFIDENCE is your confidence percentage (0-100) in the categorization
6. Use "UNKNOWN|0" if no category fits well
7. Use EXACT category names from the lists above

Example response format:
0|Groceries|85
1|Transport|92
2|UNKNOWN|0

Response:"""

            logger.info(f"[BATCH LLM] Sending request to OpenAI API (model: {self.LLM_MODEL})...")

            try:
                response = client.chat.completions.create(
                    model=self.LLM_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a financial transaction categorization expert. Respond only in the specified format, one line per transaction: INDEX|CATEGORY_NAME|CONFIDENCE"
                        },
                        {"role": "user", "content": prompt}
                    ],
                    temperature=self.LLM_TEMPERATURE,
                    max_tokens=max(150, len(batch) * 25),  # ~25 tokens per response line (includes confidence)
                    timeout=30.0  # 30 second timeout
                )

                logger.info("[BATCH LLM] Received response from OpenAI API")

                # Track tokens and cost
                input_tokens = response.usage.prompt_tokens
                output_tokens = response.usage.completion_tokens
                batch_tokens = response.usage.total_tokens
                batch_cost = self._calculate_llm_cost(input_tokens, output_tokens, self.LLM_MODEL)

                logger.info(f"[BATCH LLM] Tokens used - input: {input_tokens}, output: {output_tokens}, total: {batch_tokens}, cost: ${batch_cost:.6f}")

                total_tokens += batch_tokens
                total_cost += batch_cost

                # Parse response
                response_text = response.choices[0].message.content.strip()
                logger.info(f"[BATCH LLM] Response text:\n{response_text}")

                unknown_count = 0
                parsed_count = 0
                
                for line in response_text.split("\n"):
                    line = line.strip()
                    if not line or "|" not in line:
                        continue

                    parts = line.split("|")
                    if len(parts) < 2:
                        continue

                    try:
                        idx = int(parts[0].strip())
                        cat_name = parts[1].strip()
                        parsed_count += 1

                        if cat_name.upper() == "UNKNOWN":
                            unknown_count += 1
                            logger.debug(f"Batch LLM returned UNKNOWN for transaction {idx} (LLM couldn't confidently categorize)")
                            continue

                        # Parse confidence (default to 50 if not provided)
                        confidence = 50.0
                        if len(parts) >= 3:
                            try:
                                confidence = float(parts[2].strip())
                                confidence = max(0.0, min(100.0, confidence))  # Clamp to 0-100
                            except ValueError:
                                pass

                        # Find matching category
                        matched_cat = categories.get(cat_name.lower())
                        if matched_cat:
                            results[idx] = (matched_cat, confidence)
                            logger.debug(f"Batch LLM matched transaction {idx} to '{matched_cat.name}' (confidence: {confidence}%)")
                        else:
                            logger.warning(f"Batch LLM suggested '{cat_name}' for index {idx} but category not found")

                    except (ValueError, IndexError) as e:
                        logger.warning(f"Failed to parse batch LLM response line '{line}': {e}")
                        continue
                
                # Log summary of parsing
                if unknown_count > 0:
                    logger.info(f"[BATCH LLM] LLM returned UNKNOWN for {unknown_count} out of {parsed_count} transactions (this is normal for vague/unclear transactions)")
                if parsed_count == 0:
                    logger.warning(f"[BATCH LLM] No valid response lines parsed from LLM response. Response was: {response_text[:200]}")

                logger.info(
                    f"Batch LLM categorized {len(results)} transactions "
                    f"(tokens: {batch_tokens}, cost: ${batch_cost:.6f})"
                )

            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)
                logger.error(f"[BATCH LLM] API call failed with error: {error_type}: {error_msg}")
                
                # Provide detailed diagnostics based on error type
                error_lower = error_msg.lower()
                if "401" in error_msg or "authentication" in error_lower or "api key" in error_lower:
                    logger.error("[BATCH LLM] DIAGNOSIS: Authentication error - API key may be invalid, expired, or missing")
                elif "429" in error_msg or "rate limit" in error_lower:
                    logger.error("[BATCH LLM] DIAGNOSIS: Rate limit exceeded - API quota may be exceeded, wait and retry")
                elif "timeout" in error_lower:
                    logger.error(f"[BATCH LLM] DIAGNOSIS: Request timeout - API call took longer than 30 seconds")
                    logger.error(f"[BATCH LLM] Consider reducing batch size (current: {len(batch)} transactions)")
                elif "network" in error_lower or "connection" in error_lower or "dns" in error_lower:
                    logger.error("[BATCH LLM] DIAGNOSIS: Network connectivity issue - check internet connection")
                elif "invalid" in error_lower and "model" in error_lower:
                    logger.error(f"[BATCH LLM] DIAGNOSIS: Invalid model - check that {self.LLM_MODEL} is available")
                elif "context length" in error_lower or "token" in error_lower:
                    logger.error(f"[BATCH LLM] DIAGNOSIS: Context length exceeded - batch too large, reduce max_batch_size")
                else:
                    logger.error(f"[BATCH LLM] DIAGNOSIS: Unknown error type - see traceback for details")
                
                import traceback
                logger.error(f"[BATCH LLM] Traceback:\n{traceback.format_exc()}")
                
                # Log request details for debugging (without sensitive data)
                logger.debug(f"[BATCH LLM] Request details - Model: {self.LLM_MODEL}, Batch size: {len(batch)}, "
                           f"Max tokens: {max(150, len(batch) * 25)}, Temperature: {self.LLM_TEMPERATURE}")
                
                continue

        logger.info(f"[BATCH LLM] Completed. Total results: {len(results)}, tokens: {total_tokens}, cost: ${total_cost:.6f}")
        return results, total_tokens, total_cost

