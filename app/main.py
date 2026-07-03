"""FastAPI entrypoint for Synod."""

from fastapi import FastAPI
from app.api.routes import router

app = FastAPI(title="Synod", docs_url="/docs")
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}
