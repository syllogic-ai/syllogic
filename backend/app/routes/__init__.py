from fastapi import APIRouter
from app.routes import accounts, categories, transactions, analytics, sync, transaction_import, subscriptions, events, csv_import

api_router = APIRouter()

api_router.include_router(accounts.router, prefix="/accounts", tags=["accounts"])
api_router.include_router(categories.router, prefix="/categories", tags=["categories"])
api_router.include_router(transactions.router, prefix="/transactions", tags=["transactions"])
api_router.include_router(transaction_import.router, prefix="/transactions", tags=["transactions"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(sync.router, prefix="/sync", tags=["sync"])
api_router.include_router(subscriptions.router, prefix="/subscriptions", tags=["subscriptions"])
api_router.include_router(events.router, prefix="/events", tags=["events"])
api_router.include_router(csv_import.router, prefix="/csv-import", tags=["csv-import"])