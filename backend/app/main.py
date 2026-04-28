from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import accounts, auth, matching, sns, tax_invoices, transactions, uploads, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="TK101 AI Backend", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(accounts.router)
app.include_router(transactions.router)
app.include_router(uploads.router)
app.include_router(matching.router)
app.include_router(tax_invoices.router)
app.include_router(sns.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
