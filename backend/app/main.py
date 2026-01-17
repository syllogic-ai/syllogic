from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from app.database import engine, Base
from app.routes import api_router

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Personal Finance API",
    description="API for personal finance management",
    version="0.1.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.get("/")
def root():
    return {"message": "Personal Finance API", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "healthy"}
