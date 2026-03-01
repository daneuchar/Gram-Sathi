from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Gram Saathi API", version="0.1.0", lifespan=lifespan)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "gram-saathi"}


from app.routers import webhooks, voice, dashboard
app.include_router(webhooks.router)
app.include_router(voice.router)
app.include_router(dashboard.router)
