"""FastAPI entrypoint for Synod."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.api.webhook import router as webhook_router

app = FastAPI(title="Synod", docs_url="/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(webhook_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
