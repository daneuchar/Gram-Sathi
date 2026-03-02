import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.call_log import CallLog
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


async def _get_params(request: Request) -> dict:
    """Read params from form body (POST) or query string (GET)."""
    if request.method == "POST":
        form = await request.form()
        return dict(form)
    return dict(request.query_params)


@router.api_route("/inbound-call", methods=["GET", "POST"])
async def inbound_call(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    params = await _get_params(request)
    call_sid = params.get("CallSid", "")
    from_number = params.get("From", "")

    # Auto-create user on first call
    existing = await db.get(User, from_number)
    if not existing:
        db.add(User(phone=from_number))
        await db.flush()

    db.add(CallLog(call_sid=call_sid, phone=from_number, direction="inbound", status="in-progress"))
    await db.commit()

    ws_url = f"{settings.public_url.replace('https://', 'wss://')}/telephone/handler"
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{ws_url}" />
  </Connect>
</Response>"""

    logger.info("Inbound call %s from %s → streaming to %s", call_sid, from_number, ws_url)
    return Response(content=twiml, media_type="text/xml")


@router.api_route("/call-status", methods=["GET", "POST"])
async def call_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    params = await _get_params(request)
    call_sid = params.get("CallSid", "")
    status = params.get("CallStatus", "")
    duration = int(params.get("CallDuration", 0))

    record = await db.get(CallLog, call_sid)
    if record:
        record.status = status
        record.duration_seconds = duration
        await db.commit()

    return Response(content="<Response/>", media_type="text/xml")
