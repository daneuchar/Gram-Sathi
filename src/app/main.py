from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from app.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Gram Saathi API", version="0.1.0", lifespan=lifespan)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "gram-saathi"}


from app.routers import webhooks, dashboard
app.include_router(webhooks.router)
app.include_router(dashboard.router)
