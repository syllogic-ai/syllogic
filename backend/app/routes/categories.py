from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from uuid import UUID
import logging
import csv
import io
from decimal import Decimal

from app.database import get_db
from app.models import Category, Transaction
from app.db_helpers import get_user_id
from app.db_helpers import get_user_id
from app.schemas import (
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
    TransactionInput,
    TransactionResult,
    CategorizeTransactionRequest,
    CategorizeTransactionResponse,
    BatchCategorizeRequest,
    BatchCategorizeResponse,
    UserOverride,
)
from app.services.category_matcher import CategoryMatcher

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=List[CategoryResponse])
def list_categories(
    user_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all categories for the current user."""
    user_id = get_user_id(user_id)
    categories = db.query(Category).filter(Category.user_id == user_id).order_by(Category.name).all()
    return categories


@router.get("/{category_id}", response_model=CategoryResponse)
def get_category(
    category_id: UUID,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get a specific category by ID."""
    user_id = get_user_id(user_id)
    category = db.query(Category).filter(
        Category.id == category_id,
        Category.user_id == user_id
    ).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


@router.post("/", response_model=CategoryResponse, status_code=201)
def create_category(
    category: CategoryCreate,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Create a new category."""
    user_id = get_user_id(user_id)
    category_data = category.model_dump()
    category_data["user_id"] = user_id
    db_category = Category(**category_data)
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category


@router.patch("/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: UUID,
    updates: CategoryUpdate,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Update a category."""
    user_id = get_user_id(user_id)
    category = db.query(Category).filter(
        Category.id == category_id,
        Category.user_id == user_id
    ).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    update_data = updates.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(category, field, value)

    db.commit()
    db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=204)
def delete_category(
    category_id: UUID,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Delete a category."""
    user_id = get_user_id(user_id)
    category = db.query(Category).filter(
        Category.id == category_id,
        Category.user_id == user_id
    ).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # Set category_id and category_system_id to NULL for transactions using this category
    # Update transactions where category_id matches
    db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.category_id == category_id
    ).update({"category_id": None}, synchronize_session=False)
    
    # Update transactions where category_system_id matches
    db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.category_system_id == category_id
    ).update({"category_system_id": None}, synchronize_session=False)
    
    db.commit()

    db.delete(category)
    db.commit()
    return None


@router.get("/{category_id}/stats")
def get_category_stats(
    category_id: UUID,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get statistics for a category."""
    user_id = get_user_id(user_id)
    category = db.query(Category).filter(
        Category.id == category_id,
        Category.user_id == user_id
    ).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # Count transactions where this category is used (either as user override or system assigned)
    stats = (
        db.query(
            func.count(Transaction.id).label("count"),
            func.sum(Transaction.amount).label("total"),
        )
        .filter(
            Transaction.user_id == user_id,
            (
                (Transaction.category_id == category_id) |
                (Transaction.category_system_id == category_id)
            )
        )
        .first()
    )

    return {
        "category_id": category_id,
        "transaction_count": stats.count or 0,
        "total_amount": float(stats.total) if stats.total else 0,
    }


@router.post("/categorize", response_model=CategorizeTransactionResponse)
def categorize_transaction(
    request: CategorizeTransactionRequest, db: Session = Depends(get_db)
):
    """
    Categorize a single transaction.
    
    This is the production endpoint for categorizing transactions when new data enters the system.
    It uses the same categorization engine as the test endpoint but with a simpler interface.
    
    Example request:
    ```json
    {
        "description": "TESCO SUPERMARKET",
        "merchant": "Tesco",
        "amount": -25.50,
        "use_llm": true
    }
    ```
    
    Example response:
    ```json
    {
        "category_id": "123e4567-e89b-12d3-a456-426614174000",
        "category_name": "Groceries",
        "method": "deterministic",
        "confidence_score": 17.6,
        "matched_keywords": ["supermarket", "tesco"]
    }
    ```
    """
    try:
        # Convert user_overrides to dict format for CategoryMatcher
        user_overrides_dict = None
        if request.user_overrides:
            user_overrides_dict = [override.model_dump() for override in request.user_overrides]
        
        user_id = get_user_id()
        matcher = CategoryMatcher(
            db,
            user_id=user_id,
            user_overrides=user_overrides_dict,
            additional_instructions=request.additional_instructions
        )
        
        result = matcher.match_category_with_details(
            description=request.description,
            merchant=request.merchant,
            amount=request.amount,
            transaction_type=request.transaction_type,
            use_llm=request.use_llm
        )
        
        return CategorizeTransactionResponse(
            category_id=result.category.id if result.category else None,
            category_name=result.category.name if result.category else None,
            method=result.method,
            confidence_score=result.confidence_score,
            matched_keywords=result.matched_keywords,
            tokens_used=result.tokens_used,
            cost_usd=result.cost_usd,
        )
    except Exception as e:
        logger.error(f"[CATEGORIZE] Error categorizing transaction: {type(e).__name__}: {e}")
        import traceback
        logger.error(f"[CATEGORIZE] Traceback:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Categorization failed: {str(e)}")


@router.post("/categorize/batch", response_model=BatchCategorizeResponse)
def categorize_transactions_batch(
    request: BatchCategorizeRequest, 
    db: Session = Depends(get_db),
    user_id: Optional[str] = None
):
    """
    Categorize multiple transactions in batch.
    
    This endpoint categorizes multiple transactions efficiently by batching LLM calls.
    It supports user-defined category overrides and additional instructions.
    
    Example request:
    ```json
    {
        "transactions": [
            {"description": "TESCO SUPERMARKET", "merchant": "Tesco", "amount": -25.50},
            {"description": "UBER RIDE", "merchant": "Uber", "amount": -15.00}
        ],
        "use_llm": true
    }
    ```
    """
    try:
        logger.info(f"[CATEGORIZE] Batch categorizing {len(request.transactions)} transactions (use_llm={request.use_llm})")

        # Convert user_overrides to dict format for CategoryMatcher
        user_overrides_dict = None
        if request.user_overrides:
            user_overrides_dict = [override.model_dump() for override in request.user_overrides]
        
        # Use provided user_id or get from request context (defaults to system user if neither available)
        actual_user_id = get_user_id(user_id)
        logger.debug(f"[CATEGORIZE] Using user_id: {actual_user_id} (provided: {user_id})")
        matcher = CategoryMatcher(
            db,
            user_id=actual_user_id,
            user_overrides=user_overrides_dict,
            additional_instructions=request.additional_instructions
        )
        results = []
        unmatched_indices = []

        deterministic_count = 0

        # Phase 1: Run deterministic matching on all transactions
        logger.info("[CATEGORIZE] Phase 1: Running deterministic matching...")
        for idx, txn in enumerate(request.transactions):
            match_result = matcher.match_category_with_details(
                description=txn.description,
                merchant=txn.merchant,
                amount=txn.amount,
                transaction_type=txn.transaction_type,  # Pass transaction_type for correct type determination
                use_llm=False  # Don't use LLM in first pass
            )

            if match_result.category:
                deterministic_count += 1

            # Build initial result
            result = TransactionResult(
                description=txn.description,
                merchant=txn.merchant,
                amount=txn.amount,
                category_name=match_result.category.name if match_result.category else None,
                category_id=match_result.category.id if match_result.category else None,
                method=match_result.method if match_result.category else "none",
                confidence_score=match_result.confidence_score,
                matched_keywords=match_result.matched_keywords,
                tokens_used=None,
                cost_usd=None,
            )
            results.append(result)

            # Track unmatched for LLM batch
            if not match_result.category:
                unmatched_indices.append(idx)

        # Phase 2: Batch LLM categorization for unmatched transactions
        logger.info(f"[CATEGORIZE] Phase 1 complete. Deterministic matches: {deterministic_count}, Unmatched: {len(unmatched_indices)}")

        total_tokens = 0
        total_cost = 0.0
        llm_count = 0
        llm_errors = []
        llm_warnings = []
        llm_results = {}  # Initialize to avoid NameError

        if request.use_llm and unmatched_indices:
            logger.info(f"[CATEGORIZE] Phase 2: Running LLM batch categorization for {len(unmatched_indices)} unmatched transactions...")
            
            # Check if OpenAI client is available
            client = matcher._get_openai_client()
            if not client:
                llm_warnings.append("OpenAI API client not available. Check that OPENAI_API_KEY is set in your environment.")
                logger.warning("[CATEGORIZE] OpenAI client not available - skipping LLM categorization")
            else:
                # Prepare batch for LLM
                llm_batch = []
                logger.info(f"[CATEGORIZE] Preparing LLM batch for {len(unmatched_indices)} transactions")
                for idx in unmatched_indices:
                    txn = request.transactions[idx]
                    logger.info(f"[CATEGORIZE] Transaction {idx}: transaction_type='{txn.transaction_type}', amount={txn.amount}, description='{txn.description[:50]}...'")
                    llm_batch.append({
                        "index": idx,
                        "description": txn.description,
                        "merchant": txn.merchant,
                        "amount": float(txn.amount),
                        "transaction_type": txn.transaction_type,  # TransactionInput has transaction_type field
                    })
                logger.info(f"[CATEGORIZE] LLM batch prepared with {len(llm_batch)} items. First item keys: {list(llm_batch[0].keys()) if llm_batch else 'empty'}")
                
                try:
                    llm_results, total_tokens, total_cost = matcher.match_categories_batch_llm(llm_batch)
                    
                    if len(llm_results) < len(unmatched_indices):
                        missing = len(unmatched_indices) - len(llm_results)
                        llm_warnings.append(f"LLM was unable to categorize {missing} out of {len(unmatched_indices)} transactions.")
                except Exception as e:
                    error_type = type(e).__name__
                    error_msg = str(e)
                    error_detail = f"{error_type}: {error_msg}"
                    
                    error_lower = error_msg.lower()
                    if "401" in error_msg or "authentication" in error_lower or "api key" in error_lower:
                        error_detail = f"Authentication Error: {error_msg}. Check your OPENAI_API_KEY."
                    elif "429" in error_msg or "rate limit" in error_lower:
                        error_detail = f"Rate Limit Error: {error_msg}. Wait and retry."
                    elif "timeout" in error_lower:
                        error_detail = f"Timeout Error: {error_msg}."
                    elif "network" in error_lower or "connection" in error_lower:
                        error_detail = f"Network Error: {error_msg}."
                    
                    llm_errors.append(error_detail)
                    llm_results = {}
                    total_tokens = 0
                    total_cost = 0.0
                
                # Update results with LLM matches
                cost_per_txn = total_cost / len(unmatched_indices) if unmatched_indices else 0
                tokens_per_txn = total_tokens // len(unmatched_indices) if unmatched_indices else 0
                
                for idx in unmatched_indices:
                    if idx in llm_results:
                        category, confidence = llm_results[idx]
                        results[idx].category_id = category.id
                        results[idx].category_name = category.name
                        results[idx].method = "llm"
                        results[idx].confidence_score = confidence
                        llm_count += 1
                    
                    results[idx].tokens_used = tokens_per_txn
                    results[idx].cost_usd = cost_per_txn
        
        categorized_count = deterministic_count + llm_count
        uncategorized_count = len(request.transactions) - categorized_count
        
        logger.info(f"[CATEGORIZE] Batch complete. Categorized: {categorized_count}/{len(request.transactions)}")
        
        response_data = {
            "results": results,
            "total_transactions": len(request.transactions),
            "categorized_count": categorized_count,
            "deterministic_count": deterministic_count,
            "llm_count": llm_count,
            "uncategorized_count": uncategorized_count,
            "total_tokens_used": total_tokens,
            "total_cost_usd": total_cost,
        }
        if llm_errors:
            response_data["llm_errors"] = llm_errors
        if llm_warnings:
            response_data["llm_warnings"] = llm_warnings
        
        return BatchCategorizeResponse(**response_data)
    except Exception as e:
        logger.error(f"[CATEGORIZE] Error in batch categorization: {type(e).__name__}: {e}")
        import traceback
        logger.error(f"[CATEGORIZE] Traceback:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Batch categorization failed: {str(e)}")


def _parse_csv_line(line: str) -> List[str]:
    """Parse a CSV line handling quoted values."""
    values: List[str] = []
    current = ''
    in_quotes = False
    
    for char in line:
        if char == '"':
            in_quotes = not in_quotes
        elif char == ',' and not in_quotes:
            values.append(current.strip())
            current = ''
        else:
            current += char
    
    values.append(current.strip())
    return values


def _parse_csv_content(csv_content: str) -> List[TransactionInput]:
    """Parse CSV content and convert to TransactionInput list."""
    lines = csv_content.strip().split('\n')
    if len(lines) < 2:
        raise HTTPException(status_code=400, detail="CSV must have a header row and at least one data row")
    
    # Parse header
    header = _parse_csv_line(lines[0])
    header_lower = [h.lower().strip() for h in header]
    
    desc_idx = header_lower.index('description') if 'description' in header_lower else -1
    merchant_idx = header_lower.index('merchant') if 'merchant' in header_lower else -1
    amount_idx = header_lower.index('amount') if 'amount' in header_lower else -1
    
    if amount_idx == -1:
        raise HTTPException(status_code=400, detail='CSV must have an "amount" column')
    
    # Parse data rows
    transactions: List[TransactionInput] = []
    for i, line in enumerate(lines[1:], start=2):
        line = line.strip()
        if not line:
            continue
        
        values = _parse_csv_line(line)
        
        # Ensure we have enough values (only check amount_idx since it's required)
        if len(values) <= amount_idx:
            continue
        
        try:
            amount_str = values[amount_idx].strip() if amount_idx < len(values) else None
            if not amount_str:
                continue
            
            amount = Decimal(amount_str)
            
            description = values[desc_idx].strip() if desc_idx >= 0 and desc_idx < len(values) and values[desc_idx] else None
            merchant = values[merchant_idx].strip() if merchant_idx >= 0 and merchant_idx < len(values) and values[merchant_idx] else None
            
            transactions.append(TransactionInput(
                description=description if description else None,
                merchant=merchant if merchant else None,
                amount=amount
            ))
        except (ValueError, IndexError) as e:
            logger.warning(f"Skipping row {i}: Invalid data - {str(e)}")
            continue
    
    if not transactions:
        raise HTTPException(status_code=400, detail="No valid transactions found in CSV file")
    
    return transactions


@router.post("/categorize/batch/csv", response_model=BatchCategorizeResponse)
async def categorize_transactions_batch_csv(
    file: UploadFile = File(..., description="CSV file with transactions. Required columns: amount. Optional columns: description, merchant"),
    use_llm: bool = Form(True, description="Whether to use LLM fallback for unmatched transactions"),
    db: Session = Depends(get_db)
):
    """
    Categorize multiple transactions from a CSV file.
    
    Upload a CSV file with transaction data. The file should have:
    - **Required column**: `amount` (decimal number, negative for expenses, positive for income)
    - **Optional columns**: `description`, `merchant`
    
    **CSV Format Example:**
    ```csv
    description,merchant,amount
    TESCO SUPERMARKET,Tesco,-25.50
    UBER RIDE,Uber,-15.00
    SALARY PAYMENT,ACME Corp,3000.00
    ```
    
    You can drag and drop the CSV file directly into the file input below.
    The endpoint will parse the CSV and categorize all transactions in batch.
    """
    try:
        # Validate file type
        if not file.filename or not file.filename.endswith('.csv'):
            raise HTTPException(status_code=400, detail="File must be a CSV file (.csv extension)")
        
        # Read CSV content
        content = await file.read()
        try:
            csv_content = content.decode('utf-8')
        except UnicodeDecodeError:
            # Try with different encodings
            try:
                csv_content = content.decode('latin-1')
            except UnicodeDecodeError:
                raise HTTPException(status_code=400, detail="CSV file encoding not supported. Please use UTF-8 encoding.")
        
        # Parse CSV
        transactions = _parse_csv_content(csv_content)
        logger.info(f"[CATEGORIZE CSV] Parsed {len(transactions)} transactions from CSV file: {file.filename}")
        
        # Create batch request and call the batch categorization logic
        batch_request = BatchCategorizeRequest(
            transactions=transactions,
            use_llm=use_llm
        )
        
        # Reuse the batch categorization logic (it's a sync function)
        return categorize_transactions_batch(batch_request, db)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CATEGORIZE CSV] Error processing CSV file: {type(e).__name__}: {e}")
        import traceback
        logger.error(f"[CATEGORIZE CSV] Traceback:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error processing CSV file: {str(e)}")
