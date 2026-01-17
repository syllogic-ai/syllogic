"""
Revolut CSV import adapter.
Parses CSV files exported from Revolut app/web interface.
"""
import csv
import io
import re
import hashlib
from typing import List, Optional
from decimal import Decimal
from datetime import datetime
from app.integrations.base import BankAdapter, AccountData, TransactionData


class RevolutCSVAdapter(BankAdapter):
    """Adapter for importing Revolut transactions from CSV files."""
    
    def __init__(self, csv_content: str):
        """
        Initialize with CSV content.
        
        Args:
            csv_content: String content of the CSV file
        """
        self.csv_content = csv_content
    
    def _detect_delimiter(self) -> str:
        """Detect the delimiter used in the CSV file."""
        # Normalize line endings first
        csv_content_normalized = self.csv_content.replace('\r\n', '\n').replace('\r', '\n')
        first_line = csv_content_normalized.split('\n')[0] if '\n' in csv_content_normalized else csv_content_normalized
        
        # Check for expected Revolut header pattern
        # Tab-separated: "Type\tProduct\tStarted Date..."
        # Comma-separated: "Type,Product,Started Date..."
        if 'Type\tProduct\tStarted Date' in first_line or 'Type\tProduct\t' in first_line:
            return '\t'
        elif 'Type,Product,Started Date' in first_line or 'Type,Product,' in first_line:
            return ','
        
        # Count delimiters in first few data rows
        lines = csv_content_normalized.split('\n')[:5]
        tab_counts = []
        comma_counts = []
        
        for line in lines[1:]:  # Skip header
            if line.strip():
                tab_counts.append(line.count('\t'))
                comma_counts.append(line.count(','))
        
        if tab_counts and max(tab_counts) >= 5:
            return '\t'
        elif comma_counts and max(comma_counts) >= 5:
            return ','
        
        # Try to sniff the delimiter as fallback
        sniffer = csv.Sniffer()
        sample = csv_content_normalized[:2048] if len(csv_content_normalized) > 2048 else csv_content_normalized
        try:
            delimiter = sniffer.sniff(sample, delimiters='\t,').delimiter
            return delimiter
        except:
            # Default to comma if we can't detect (most common)
            return ','
    
    def fetch_accounts(self) -> List[AccountData]:
        """
        Extract account information from CSV.
        Revolut CSV typically doesn't have account info in the file,
        so we infer it from the transactions.
        Also extracts the latest balance from the Balance column.
        """
        # Detect delimiter - try both tab and comma
        delimiter = self._detect_delimiter()
        # Normalize line endings (handle Windows \r\n, Mac \r, Unix \n)
        csv_content_normalized = self.csv_content.replace('\r\n', '\n').replace('\r', '\n')
        reader = csv.DictReader(io.StringIO(csv_content_normalized), delimiter=delimiter)
        accounts = {}
        
        for row in reader:
            # Try to extract account identifier from CSV
            # Revolut CSV format may vary, so we'll use a generic account
            account_key = row.get('Account') or row.get('Product', 'Current')
            if account_key not in accounts:
                # Infer account type from transactions
                # Most Revolut accounts are checking accounts
                currency = row.get('Currency') or row.get('currency', 'EUR')
                # Normalize account name: "Current" -> "Revolut Account"
                if account_key.lower() == 'current':
                    display_name = "Revolut Account"
                else:
                    display_name = f"Revolut {account_key}"
                
                accounts[account_key] = AccountData(
                    external_id=account_key,
                    name=display_name,
                    account_type="checking",
                    institution="Revolut",
                    currency=currency,
                    metadata={'source': 'csv_import'}
                )
            
            # Note: balance_current removed - balances are now calculated via functional_balance
        
        # Return accounts if found, otherwise return empty list (don't create default)
        return list(accounts.values())
    
    def fetch_transactions(
        self,
        account_external_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[TransactionData]:
        """Parse transactions from CSV content."""
        transactions = []
        
        # Detect and use appropriate delimiter
        delimiter = self._detect_delimiter()
        # Normalize line endings (handle Windows \r\n, Mac \r, Unix \n)
        csv_content_normalized = self.csv_content.replace('\r\n', '\n').replace('\r', '\n')
        
        reader = csv.DictReader(io.StringIO(csv_content_normalized), delimiter=delimiter)
        
        # Debug: Check if headers are parsed correctly
        if reader.fieldnames and len(reader.fieldnames) > 1:
            print(f"DEBUG: CSV headers detected with delimiter '{delimiter}': {reader.fieldnames}")
        else:
            print(f"DEBUG: WARNING - Headers not parsed correctly. Fieldnames: {reader.fieldnames}")
            first_line = csv_content_normalized.split('\n')[0] if '\n' in csv_content_normalized else csv_content_normalized
            print(f"DEBUG: First line of CSV (first 200 chars): {first_line[:200]}")
            print(f"DEBUG: Tab count: {first_line.count(chr(9))}, Comma count: {first_line.count(',')}")
            
            # Try the other delimiter as fallback
            alt_delimiter = ',' if delimiter == '\t' else '\t'
            print(f"DEBUG: Trying alternative delimiter '{alt_delimiter}'...")
            reader = csv.DictReader(io.StringIO(csv_content_normalized), delimiter=alt_delimiter)
            if reader.fieldnames and len(reader.fieldnames) > 1:
                print(f"DEBUG: Success with alternative delimiter! Headers: {reader.fieldnames}")
                delimiter = alt_delimiter
        
        row_count = 0
        parsed_count = 0
        skipped_count = 0
        
        for row in reader:
            row_count += 1
            try:
                # Parse transaction based on common Revolut CSV formats
                # Format may vary, so we try multiple field name variations
                transaction = self._parse_transaction_row(row, account_external_id)
                
                if transaction:
                    # Apply date filters if provided
                    if start_date and transaction.booked_at < start_date:
                        skipped_count += 1
                        continue
                    if end_date and transaction.booked_at > end_date:
                        skipped_count += 1
                        continue
                    
                    transactions.append(transaction)
                    parsed_count += 1
                else:
                    skipped_count += 1
                    # Log why transaction was skipped (first few only)
                    if skipped_count <= 3:
                        print(f"DEBUG: Skipped row {row_count}: Missing required fields. Row keys: {list(row.keys())}, sample values: {list(row.values())[:3] if row else []}")
            except Exception as e:
                # Skip malformed rows but log the error
                skipped_count += 1
                print(f"Error parsing transaction row {row_count}: {e}, row keys: {list(row.keys())}")
                continue
        
        print(f"DEBUG: Processed {row_count} rows, parsed {parsed_count} transactions, skipped {skipped_count}")
        
        return transactions
    
    def _parse_transaction_row(self, row: dict, account_external_id: str) -> Optional[TransactionData]:
        """Parse a single CSV row into TransactionData."""
        # Try different CSV format variations
        # Common Revolut CSV formats:
        # Format 1: Type, Product, Started Date, Completed Date, Description, Amount, Fee, Currency, State
        # Format 2: Date, Description, Amount, Currency, etc.
        # Format 3: Completed Date, Reference, Paid Out (EUR), Paid In (EUR), Exchange Out, Exchange In, etc.
        
        # Debug: Check row structure - if only 1 key, CSV parsing failed
        if len(row.keys()) == 1:
            print(f"DEBUG: WARNING - Row has only 1 key, CSV may not be parsed correctly. Keys: {list(row.keys())}")
            print(f"DEBUG: First key value (first 200 chars): {str(list(row.values())[0])[:200]}")
            return None
        
        # Try to find date field (various names - check case-insensitive)
        date_str = None
        for key in row.keys():
            key_lower = key.lower()
            if 'completed' in key_lower and 'date' in key_lower:
                date_str = row.get(key)
                break
            elif 'started' in key_lower and 'date' in key_lower:
                date_str = row.get(key)
                break
            elif key_lower == 'date' or 'transaction date' in key_lower or 'booked date' in key_lower:
                date_str = row.get(key)
                break
        
        # Fallback to explicit field names
        if not date_str:
            date_str = (
                row.get('Completed Date') or 
                row.get('Started Date') or 
                row.get('Date') or 
                row.get('Transaction Date') or
                row.get('Booked Date') or
                row.get('completed_date') or
                row.get('started_date')
            )
        
        if not date_str:
            return None
        
        # Parse date (try multiple formats)
        booked_at = self._parse_date(date_str)
        if not booked_at:
            return None
        
        # Get amount - try multiple field variations
        amount_str = None
        for key in row.keys():
            key_lower = key.lower()
            if key_lower == 'amount':
                amount_str = row.get(key)
                break
            elif 'paid out' in key_lower or 'paid in' in key_lower:
                # Revolut sometimes uses "Paid Out (EUR)" and "Paid In (EUR)" columns
                paid_out = row.get(key) or '0'
                paid_in = row.get(key.replace('Out', 'In').replace('out', 'in')) or '0'
                # Try to get the corresponding "In" column
                for other_key in row.keys():
                    if 'paid in' in other_key.lower() and key != other_key:
                        paid_in = row.get(other_key) or '0'
                        break
                # Use paid_in if positive, negative paid_out if negative
                try:
                    out_val = Decimal(str(paid_out).replace(',', '').strip() or '0')
                    in_val = Decimal(str(paid_in).replace(',', '').strip() or '0')
                    if in_val > 0:
                        amount_str = str(in_val)
                    elif out_val > 0:
                        amount_str = str(-out_val)
                    break
                except:
                    pass
        
        # Fallback to explicit field names
        if not amount_str:
            amount_str = (
                row.get('Amount') or 
                row.get('Transaction Amount') or
                row.get('amount') or
                row.get('transaction_amount')
            )
        
        if not amount_str:
            return None
        
        try:
            # Remove currency symbols, whitespace, and handle various formats
            amount_str = str(amount_str).replace(',', '').replace('€', '').replace('$', '').replace('£', '').strip()
            # Handle empty strings
            if not amount_str or amount_str == '':
                return None
            amount = Decimal(amount_str)
        except (ValueError, AttributeError, TypeError):
            return None
        
        # Determine transaction type
        transaction_type = "credit" if amount >= 0 else "debit"
        
        # Get description - try case-insensitive matching
        description = None
        for key in row.keys():
            key_lower = key.lower()
            if 'description' in key_lower or key_lower == 'note' or key_lower == 'reference':
                description = row.get(key)
                break
        
        # Fallback to explicit field names
        if not description:
            description = (
                row.get('Description') or 
                row.get('Transaction Description') or 
                row.get('Note') or
                row.get('Reference') or
                row.get('Merchant') or
                row.get('description') or
                row.get('reference') or
                ''
            )
        
        description = str(description).strip() if description else ''
        
        # Get merchant (may be in description or separate field)
        merchant = None
        for key in row.keys():
            key_lower = key.lower()
            if key_lower == 'merchant' or 'counterparty' in key_lower:
                merchant = row.get(key)
                break
        
        # Fallback to explicit field names
        if not merchant:
            merchant = (
                row.get('Merchant') or 
                row.get('Counterparty') or
                row.get('merchant') or
                row.get('counterparty') or
                None
            )
        
        # Extract merchant from description if not separate
        if not merchant and description:
            # Try to extract merchant name from description
            # Common patterns: "MERCHANT NAME", "Merchant Name - Description"
            parts = description.split(' - ')
            if len(parts) > 1:
                merchant = parts[0].strip()
            elif ' * ' in description:
                # Some formats use " * " as separator
                parts = description.split(' * ')
                if len(parts) > 1:
                    merchant = parts[0].strip()
        
        # Get currency - try to find currency column
        currency = 'EUR'  # default
        for key in row.keys():
            key_lower = key.lower()
            if key_lower == 'currency':
                currency = row.get(key, 'EUR')
                break
            elif 'paid out' in key_lower or 'paid in' in key_lower:
                # Extract currency from column name like "Paid Out (EUR)"
                match = re.search(r'\(([A-Z]{3})\)', key)
                if match:
                    currency = match.group(1)
                    break
        
        # Fallback
        if currency == 'EUR':
            currency = row.get('Currency', row.get('currency', 'EUR'))
        
        # Get state/pending status
        state = None
        for key in row.keys():
            if key.lower() == 'state' or 'status' in key.lower():
                state = row.get(key)
                break
        
        if not state:
            state = row.get('State', row.get('state', ''))
        
        pending = False
        if state:
            state_lower = str(state).lower()
            pending = state_lower in ['pending', 'processing', 'in progress']
        
        # Create external ID from date, amount, and description (use a hash for uniqueness)
        unique_str = f"{booked_at.isoformat()}_{amount}_{description[:50]}"
        external_id = hashlib.md5(unique_str.encode()).hexdigest()
        
        return TransactionData(
            external_id=external_id,
            account_external_id=account_external_id,
            amount=amount,
            currency=currency,
            description=description,
            merchant=merchant,
            booked_at=booked_at,
            transaction_type=transaction_type,
            pending=pending,
            metadata={'source': 'revolut_csv', 'raw_row': row}
        )
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string in various formats."""
        if not date_str:
            return None
        
        date_str = str(date_str).strip()
        
        # Skip if it's just hash symbols (masked dates)
        if date_str.startswith('#'):
            return None
        
        # Try common date formats
        # Note: Revolut uses DD/MM/YYYY format
        formats = [
            '%d/%m/%Y %H:%M:%S',  # 02/01/2025 20:48:05
            '%d/%m/%Y %H:%M',     # 02/01/2025 20:48 (most common in Revolut)
            '%d/%m/%Y',           # 02/01/2025
            '%Y-%m-%d %H:%M:%S',  # 2025-01-02 20:48:05
            '%Y-%m-%d %H:%M',     # 2025-01-02 20:48
            '%Y-%m-%d',           # 2025-01-02
            '%d-%m-%Y %H:%M:%S',  # 02-01-2025 20:48:05
            '%d-%m-%Y %H:%M',     # 02-01-2025 20:48
            '%d-%m-%Y',           # 02-01-2025
            '%Y/%m/%d %H:%M:%S',  # 2025/01/02 20:48:05
            '%Y/%m/%d %H:%M',     # 2025/01/02 20:48
            '%Y/%m/%d',           # 2025/01/02
            '%m/%d/%Y %H:%M:%S',  # 01/02/2025 20:48:05
            '%m/%d/%Y %H:%M',     # 01/02/2025 20:48
            '%m/%d/%Y',           # 01/02/2025
            '%d.%m.%Y %H:%M:%S',  # 02.01.2025 20:48:05
            '%d.%m.%Y %H:%M',     # 02.01.2025 20:48
            '%d.%m.%Y',           # 02.01.2025
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        # If all formats fail, log it for debugging
        print(f"DEBUG: Could not parse date: '{date_str}'")
        return None
    
    def normalize_transaction(self, raw: dict) -> TransactionData:
        """Convert raw transaction dict to TransactionData."""
        # This is already handled in _parse_transaction_row
        # But we implement it for the interface
        return self._parse_transaction_row(raw, raw.get('account_external_id', 'default'))

