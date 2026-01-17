"""
Streamlit app for monitoring the database.
Run with: streamlit run postgres_migration/monitor_db.py
(From the backend directory)
Or: cd backend && streamlit run postgres_migration/monitor_db.py
"""
import sys
from pathlib import Path

# Add parent directory to path so we can import app modules
# This allows running from either backend/ or backend/postgres_migration/
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import streamlit as st
import pandas as pd
from sqlalchemy import text
from app.database import SessionLocal, engine
from app.models import (
    User, Account, Category, Transaction,
    CategorizationRule, BankConnection, ExchangeRate
)
from datetime import datetime, timedelta

# Page config
st.set_page_config(
    page_title="Database Monitor",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'db_session' not in st.session_state:
    st.session_state.db_session = SessionLocal()


def get_table_data(model, filters=None):
    """Get data from a table and return as DataFrame."""
    try:
        query = st.session_state.db_session.query(model)
        
        if filters:
            for key, value in filters.items():
                if value is not None and value != "":
                    if hasattr(model, key):
                        query = query.filter(getattr(model, key) == value)
        
        data = query.all()
        
        # Convert to list of dicts
        records = []
        for record in data:
            record_dict = {}
            for column in model.__table__.columns:
                value = getattr(record, column.name)
                # Handle datetime and UUID serialization
                if isinstance(value, datetime):
                    value = value.isoformat()
                elif hasattr(value, '__str__'):
                    value = str(value)
                record_dict[column.name] = value
            records.append(record_dict)
        
        return pd.DataFrame(records)
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return pd.DataFrame()


def get_table_stats():
    """Get statistics about all tables."""
    stats = {}
    try:
        with engine.connect() as conn:
            tables = ['users', 'accounts', 'categories', 'transactions', 
                     'categorization_rules', 'bank_connections', 'exchange_rates']
            
            for table in tables:
                try:
                    result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    count = result.scalar()
                    stats[table] = count
                except Exception as e:
                    # Table might not exist yet
                    stats[table] = 0
    except Exception as e:
        st.error(f"Error getting stats: {e}")
    
    return stats


# Sidebar
st.sidebar.title("📊 Database Monitor")
st.sidebar.markdown("---")

# Refresh button
if st.sidebar.button("🔄 Refresh All Data", use_container_width=True):
    st.rerun()

# Database stats
st.sidebar.markdown("### 📈 Table Statistics")
stats = get_table_stats()
for table, count in stats.items():
    st.sidebar.metric(table.replace('_', ' ').title(), count)

st.sidebar.markdown("---")

# Database connection info
st.sidebar.markdown("### 🔌 Connection Info")
try:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version()"))
        db_version = result.scalar()
        st.sidebar.text(f"PostgreSQL\n{db_version.split(',')[0]}")
except:
    st.sidebar.text("PostgreSQL\nConnected")

# Main content
st.title("📊 Database Monitor")
st.markdown("Monitor and explore your database tables")

# Create tabs
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "👥 Users",
    "💳 Accounts",
    "📁 Categories",
    "💰 Transactions",
    "🎯 Categorization Rules",
    "🏦 Bank Connections",
    "💱 Exchange Rates"
])

# Tab 1: Users
with tab1:
    st.header("Users Table")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"**Total Users:** {stats.get('users', 0)}")
    with col2:
        if st.button("🔄 Refresh", key="refresh_users"):
            st.rerun()
    
    df_users = get_table_data(User)
    
    if not df_users.empty:
        st.dataframe(
            df_users,
            width='stretch',
            hide_index=True
        )
        
        # User details
        if len(df_users) > 0:
            st.markdown("### User Details")
            selected_user = st.selectbox(
                "Select a user to view details:",
                df_users['id'].tolist(),
                key="user_select"
            )
            
            if selected_user:
                user_data = df_users[df_users['id'] == selected_user].iloc[0]
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Email", user_data.get('email', 'N/A'))
                with col2:
                    st.metric("Name", user_data.get('name', 'N/A'))
                with col3:
                    st.metric("Email Verified", "✓" if user_data.get('email_verified') else "✗")
                with col4:
                    st.metric("Functional Currency", user_data.get('functional_currency', 'EUR'))
    else:
        st.info("No users found in the database.")

# Tab 2: Accounts
with tab2:
    st.header("Accounts Table")
    
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        st.markdown(f"**Total Accounts:** {stats.get('accounts', 0)}")
    with col2:
        user_filter = st.selectbox(
            "Filter by User:",
            ["All"] + (df_users['id'].tolist() if not df_users.empty else []),
            key="account_user_filter"
        )
    with col3:
        if st.button("🔄 Refresh", key="refresh_accounts"):
            st.rerun()
    
    filters = {}
    if user_filter != "All":
        filters['user_id'] = user_filter
    
    df_accounts = get_table_data(Account, filters)
    
    if not df_accounts.empty:
        # Summary metrics
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        with col1:
            active_count = len(df_accounts[df_accounts.get('is_active', True) == True])
            st.metric("Active Accounts", active_count)
        with col2:
            if 'functional_balance' in df_accounts.columns:
                # Convert to numeric, handling string/decimal types
                balances = pd.to_numeric(df_accounts['functional_balance'], errors='coerce')
                total_balance = float(balances.sum()) if not balances.isna().all() else 0.0
            else:
                total_balance = 0.0
            st.metric("Total Functional Balance", f"€{total_balance:,.2f}")
        with col3:
            if 'functional_balance' in df_accounts.columns:
                func_balances = pd.to_numeric(df_accounts['functional_balance'], errors='coerce')
                total_func_balance = float(func_balances.sum()) if not func_balances.isna().all() else 0.0
                st.metric("Total Functional Balance", f"€{total_func_balance:,.2f}")
            else:
                st.metric("Total Functional Balance", "N/A")
        with col4:
            if 'starting_balance' in df_accounts.columns:
                starting_balances = pd.to_numeric(df_accounts['starting_balance'], errors='coerce')
                total_starting = float(starting_balances.sum()) if not starting_balances.isna().all() else 0.0
                st.metric("Total Starting Balance", f"€{total_starting:,.2f}")
            else:
                st.metric("Total Starting Balance", "N/A")
        with col5:
            providers = df_accounts['provider'].nunique() if 'provider' in df_accounts.columns else 0
            st.metric("Providers", providers)
        with col6:
            currencies = df_accounts['currency'].nunique() if 'currency' in df_accounts.columns else 0
            st.metric("Currencies", currencies)
        
        # Show warning if functional_balance is not calculated
        if 'functional_balance' in df_accounts.columns:
            func_balances = pd.to_numeric(df_accounts['functional_balance'], errors='coerce')
            null_count = func_balances.isna().sum()
            if null_count > 0:
                st.warning(f"⚠️ {null_count} account(s) have NULL functional_balance. Run `POST /api/accounts/calculate-balances` to populate them.")
        
        st.dataframe(
            df_accounts,
            width='stretch',
            hide_index=True
        )
    else:
        st.info("No accounts found in the database.")

# Tab 3: Categories
with tab3:
    st.header("Categories Table")
    
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        st.markdown(f"**Total Categories:** {stats.get('categories', 0)}")
    with col2:
        user_filter = st.selectbox(
            "Filter by User:",
            ["All"] + (df_users['id'].tolist() if not df_users.empty else []),
            key="category_user_filter"
        )
    with col3:
        if st.button("🔄 Refresh", key="refresh_categories"):
            st.rerun()
    
    filters = {}
    if user_filter != "All":
        filters['user_id'] = user_filter
    
    df_categories = get_table_data(Category, filters)
    
    if not df_categories.empty:
        # Summary by type
        if 'category_type' in df_categories.columns:
            type_counts = df_categories['category_type'].value_counts()
            col1, col2, col3 = st.columns(3)
            for idx, (cat_type, count) in enumerate(type_counts.items()):
                with [col1, col2, col3][idx % 3]:
                    st.metric(f"{cat_type.title()} Categories", count)
        
        st.dataframe(
            df_categories,
            width='stretch',
            hide_index=True
        )
    else:
        st.info("No categories found in the database.")

# Tab 4: Transactions
with tab4:
    st.header("Transactions Table")
    
    col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 1])
    with col1:
        st.markdown(f"**Total Transactions:** {stats.get('transactions', 0)}")
    with col2:
        user_filter = st.selectbox(
            "Filter by User:",
            ["All"] + (df_users['id'].tolist() if not df_users.empty else []),
            key="transaction_user_filter"
        )
    
    # Get accounts for account filter (filtered by user if user filter is set)
    account_filters = {}
    if user_filter != "All":
        account_filters['user_id'] = user_filter
    df_accounts_for_filter = get_table_data(Account, account_filters)
    
    with col3:
        # Create account options with names
        if not df_accounts_for_filter.empty:
            account_options = ["All"] + df_accounts_for_filter['id'].tolist()
            account_names = {acc_id: acc_name for acc_id, acc_name in 
                           zip(df_accounts_for_filter['id'], df_accounts_for_filter['name'])}
            account_filter = st.selectbox(
                "Filter by Account:",
                account_options,
                key="transaction_account_filter",
                format_func=lambda x: f"{account_names.get(x, 'Unknown')} ({str(x)[:8]}...)" if x != "All" and x in account_names else x
            )
        else:
            account_filter = st.selectbox(
                "Filter by Account:",
                ["All"],
                key="transaction_account_filter"
            )
    
    with col4:
        date_range = st.selectbox(
            "Date Range:",
            ["All", "Last 7 days", "Last 30 days", "Last 90 days"],
            key="transaction_date_filter"
        )
    with col5:
        if st.button("🔄 Refresh", key="refresh_transactions"):
            st.rerun()
    
    filters = {}
    if user_filter != "All":
        filters['user_id'] = user_filter
    if account_filter != "All":
        filters['account_id'] = account_filter
    
    df_transactions = get_table_data(Transaction, filters)
    
    if not df_transactions.empty:
        # Apply date filter
        if date_range != "All" and 'booked_at' in df_transactions.columns:
            df_transactions['booked_at'] = pd.to_datetime(df_transactions['booked_at'])
            cutoff_date = datetime.now() - timedelta(
                days=7 if date_range == "Last 7 days" else 
                     30 if date_range == "Last 30 days" else 90
            )
            df_transactions = df_transactions[df_transactions['booked_at'] >= cutoff_date]
        
        # Summary metrics
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            if 'amount' in df_transactions.columns:
                amounts = pd.to_numeric(df_transactions['amount'], errors='coerce')
                total_amount = float(amounts.sum()) if not amounts.isna().all() else 0.0
            else:
                total_amount = 0.0
            st.metric("Total Amount", f"€{total_amount:,.2f}")
        with col2:
            if 'functional_amount' in df_transactions.columns:
                func_amounts = pd.to_numeric(df_transactions['functional_amount'], errors='coerce')
                total_func_amount = float(func_amounts.sum()) if not func_amounts.isna().all() else 0.0
                # Get user's functional currency if available
                user_func_currency = "EUR"  # Default
                if user_filter != "All" and not df_users.empty:
                    user_data = df_users[df_users['id'] == user_filter]
                    if not user_data.empty:
                        user_func_currency = user_data.iloc[0].get('functional_currency', 'EUR') or 'EUR'
                st.metric("Total Functional Amount", f"{user_func_currency} {total_func_amount:,.2f}")
            else:
                st.metric("Total Functional Amount", "N/A")
        with col3:
            if 'amount' in df_transactions.columns:
                amounts = pd.to_numeric(df_transactions['amount'], errors='coerce')
                income = float(amounts[amounts > 0].sum()) if not amounts.isna().all() else 0.0
            else:
                income = 0.0
            st.metric("Total Income", f"€{income:,.2f}")
        with col4:
            if 'amount' in df_transactions.columns:
                amounts = pd.to_numeric(df_transactions['amount'], errors='coerce')
                expenses = abs(float(amounts[amounts < 0].sum())) if not amounts.isna().all() else 0.0
            else:
                expenses = 0.0
            st.metric("Total Expenses", f"€{expenses:,.2f}")
        with col5:
            categorized = len(df_transactions[
                (df_transactions['category_id'].notna()) | 
                (df_transactions['category_system_id'].notna())
            ]) if 'category_id' in df_transactions.columns else 0
            st.metric("Categorized", f"{categorized}/{len(df_transactions)}")
        
        # Show functional_amount statistics if column exists
        if 'functional_amount' in df_transactions.columns:
            func_amounts = pd.to_numeric(df_transactions['functional_amount'], errors='coerce')
            null_count = func_amounts.isna().sum()
            if null_count > 0:
                st.warning(f"⚠️ {null_count} transactions have NULL functional_amount. Run `update_functional_amounts.py` to populate them.")
        
        # Search
        search_term = st.text_input("🔍 Search transactions:", key="transaction_search")
        if search_term:
            mask = (
                df_transactions['description'].astype(str).str.contains(search_term, case=False, na=False) |
                df_transactions['merchant'].astype(str).str.contains(search_term, case=False, na=False)
            )
            df_transactions = df_transactions[mask]
        
        st.dataframe(
            df_transactions,
            width='stretch',
            hide_index=True,
            height=400
        )
    else:
        st.info("No transactions found in the database.")

# Tab 5: Categorization Rules
with tab5:
    st.header("Categorization Rules Table")
    
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        st.markdown(f"**Total Rules:** {stats.get('categorization_rules', 0)}")
    with col2:
        user_filter = st.selectbox(
            "Filter by User:",
            ["All"] + (df_users['id'].tolist() if not df_users.empty else []),
            key="rule_user_filter"
        )
    with col3:
        if st.button("🔄 Refresh", key="refresh_rules"):
            st.rerun()
    
    filters = {}
    if user_filter != "All":
        filters['user_id'] = user_filter
    
    df_rules = get_table_data(CategorizationRule, filters)
    
    if not df_rules.empty:
        active_count = len(df_rules[df_rules.get('is_active', True) == True])
        st.metric("Active Rules", active_count)
        
        st.dataframe(
            df_rules,
            width='stretch',
            hide_index=True
        )
    else:
        st.info("No categorization rules found in the database.")

# Tab 6: Bank Connections
with tab6:
    st.header("Bank Connections Table")
    
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        st.markdown(f"**Total Connections:** {stats.get('bank_connections', 0)}")
    with col2:
        user_filter = st.selectbox(
            "Filter by User:",
            ["All"] + (df_users['id'].tolist() if not df_users.empty else []),
            key="connection_user_filter"
        )
    with col3:
        if st.button("🔄 Refresh", key="refresh_connections"):
            st.rerun()
    
    filters = {}
    if user_filter != "All":
        filters['user_id'] = user_filter
    
    df_connections = get_table_data(BankConnection, filters)
    
    if not df_connections.empty:
        # Status summary
        if 'status' in df_connections.columns:
            status_counts = df_connections['status'].value_counts()
            cols = st.columns(len(status_counts))
            for idx, (status, count) in enumerate(status_counts.items()):
                with cols[idx]:
                    st.metric(f"{status.title()}", count)
        
        st.dataframe(
            df_connections,
            width='stretch',
            hide_index=True
        )
    else:
        st.info("No bank connections found in the database.")

# Tab 7: Exchange Rates
with tab7:
    st.header("Exchange Rates Table")
    
    col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
    with col1:
        st.markdown(f"**Total Rates:** {stats.get('exchange_rates', 0)}")
    with col2:
        base_currency_filter = st.selectbox(
            "Filter by Base Currency:",
            ["All", "EUR", "USD", "GBP", "JPY", "INR"],
            key="exchange_base_filter"
        )
    with col3:
        target_currency_filter = st.selectbox(
            "Filter by Target Currency:",
            ["All", "EUR", "USD"],
            key="exchange_target_filter"
        )
    with col4:
        if st.button("🔄 Refresh", key="refresh_exchange_rates"):
            st.rerun()
    
    df_exchange_rates = get_table_data(ExchangeRate)
    
    if not df_exchange_rates.empty:
        # Apply filters
        if base_currency_filter != "All":
            df_exchange_rates = df_exchange_rates[df_exchange_rates['base_currency'] == base_currency_filter]
        if target_currency_filter != "All":
            df_exchange_rates = df_exchange_rates[df_exchange_rates['target_currency'] == target_currency_filter]
        
        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            unique_dates = df_exchange_rates['date'].nunique() if 'date' in df_exchange_rates.columns else 0
            st.metric("Unique Dates", unique_dates)
        with col2:
            unique_base = df_exchange_rates['base_currency'].nunique() if 'base_currency' in df_exchange_rates.columns else 0
            st.metric("Base Currencies", unique_base)
        with col3:
            unique_target = df_exchange_rates['target_currency'].nunique() if 'target_currency' in df_exchange_rates.columns else 0
            st.metric("Target Currencies", unique_target)
        with col4:
            if 'date' in df_exchange_rates.columns and len(df_exchange_rates) > 0:
                df_exchange_rates['date'] = pd.to_datetime(df_exchange_rates['date'])
                latest_date = df_exchange_rates['date'].max()
                st.metric("Latest Rate Date", latest_date.strftime("%Y-%m-%d") if pd.notna(latest_date) else "N/A")
            else:
                st.metric("Latest Rate Date", "N/A")
        
        # Date range filter
        if 'date' in df_exchange_rates.columns and len(df_exchange_rates) > 0:
            df_exchange_rates['date'] = pd.to_datetime(df_exchange_rates['date'])
            date_range = st.selectbox(
                "Date Range:",
                ["All", "Last 7 days", "Last 30 days", "Last 90 days"],
                key="exchange_date_filter"
            )
            
            if date_range != "All":
                cutoff_date = datetime.now() - timedelta(
                    days=7 if date_range == "Last 7 days" else 
                         30 if date_range == "Last 30 days" else 90
                )
                df_exchange_rates = df_exchange_rates[df_exchange_rates['date'] >= cutoff_date]
        
        # Convert rate to numeric for display
        if 'rate' in df_exchange_rates.columns:
            df_exchange_rates['rate'] = pd.to_numeric(df_exchange_rates['rate'], errors='coerce')
        
        # Sort by date descending
        if 'date' in df_exchange_rates.columns:
            df_exchange_rates = df_exchange_rates.sort_values('date', ascending=False)
        
        st.dataframe(
            df_exchange_rates,
            width='stretch',
            hide_index=True,
            height=400
        )
        
        # Show rate statistics by currency pair
        if len(df_exchange_rates) > 0 and 'base_currency' in df_exchange_rates.columns and 'target_currency' in df_exchange_rates.columns:
            st.markdown("### Rate Statistics by Currency Pair")
            currency_pairs = df_exchange_rates.groupby(['base_currency', 'target_currency'])
            
            for (base, target), group in currency_pairs:
                if 'rate' in group.columns:
                    rates = pd.to_numeric(group['rate'], errors='coerce').dropna()
                    if len(rates) > 0:
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric(f"{base}/{target} - Min", f"{rates.min():.6f}")
                        with col2:
                            st.metric(f"{base}/{target} - Max", f"{rates.max():.6f}")
                        with col3:
                            st.metric(f"{base}/{target} - Avg", f"{rates.mean():.6f}")
                        with col4:
                            st.metric(f"{base}/{target} - Count", len(rates))
    else:
        st.info("No exchange rates found in the database.")
        st.markdown("""
        **Note:** Exchange rates are synced automatically when you run `seed_data.py` 
        or manually via the `/api/exchange-rates/sync` endpoint.
        """)

# Footer
st.markdown("---")
st.markdown("**Database Monitor** - Real-time database monitoring tool")

# Cleanup on exit
if st.sidebar.button("🔌 Close Connection"):
    st.session_state.db_session.close()
    st.session_state.db_session = None
    st.success("Database connection closed.")
