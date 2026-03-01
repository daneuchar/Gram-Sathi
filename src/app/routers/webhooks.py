import asyncio
import logging

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import is_rate_limited
from app.config import settings
from app.database import get_db
from app.models.call_log import CallLog

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


async def trigger_callback(phone: str) -> None:
    """Sleep 5 s then POST an outbound call to Exotel."""
    await asyncio.sleep(5)
    url = (
        f"https://{settings.exotel_api_key}:{settings.exotel_api_token}"
        f"@api.exotel.com/v1/Accounts/{settings.exotel_account_sid}/Calls/connect"
    )
    payload = {
        "From": settings.exotel_phone_number,
        "To": phone,
        "CallerId": settings.exotel_phone_number,
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, data=payload, timeout=30)
            resp.raise_for_status()
            logger.info("Outbound call triggered for %s: %s", phone, resp.status_code)
    except httpx.HTTPError:
        logger.exception("Failed to trigger callback for %s", phone)


@router.post("/missed-call")
async def missed_call_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    CallSid: str = Form(...),
    From: str = Form(...),
    Status: str = Form(default="missed"),
):
    # Persist call log
    call_log = CallLog(
        call_sid=CallSid,
        phone=From,
        direction="inbound",
        status=Status,
    )
    db.add(call_log)
    await db.commit()

    # Rate-limit: one callback per phone per 60 s
    if is_rate_limited(f"callback:{From}"):
        logger.info("Rate-limited duplicate callback for %s", From)
        return {"status": "rate_limited"}

    background_tasks.add_task(trigger_callback, From)
    return {"status": "callback_scheduled"}


@router.post("/call-status")
async def call_status_webhook(
    db: AsyncSession = Depends(get_db),
    CallSid: str = Form(...),
    Status: str = Form(...),
    Duration: int = Form(default=0),
):
    result = await db.get(CallLog, CallSid)
    if result:
        result.status = Status
        result.duration_seconds = Duration
        await db.commit()
    return {"status": "ok"}
