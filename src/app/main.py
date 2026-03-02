from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastrtc import Stream

from app.database import init_db
from app.handlers.gram_saathi import GramSaathiHandler


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Gram Saathi API", version="0.1.0", lifespan=lifespan)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "gram-saathi"}


# FastRTC mounts all voice endpoints:
#   POST /telephone/incoming  — Twilio TwiML webhook
#   WS   /telephone/handler   — Twilio Media Stream WebSocket
#   POST /webrtc/offer        — browser WebRTC signalling
#   GET  /                    — built-in browser demo UI
stream = Stream(
    GramSaathiHandler(),
    modality="audio",
    mode="send-receive",
)
stream.mount(app)

from app.routers import webhooks, dashboard
app.include_router(webhooks.router)
app.include_router(dashboard.router)
