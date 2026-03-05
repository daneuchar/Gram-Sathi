import asyncio
import logging
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from livekit.api import LiveKitAPI, DeleteRoomRequest
from pydantic import BaseModel
from sqlalchemy import select, func, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.call_log import CallLog
from app.models.conversation import ConversationTurn
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _mask_phone(phone: str | None) -> str:
    if not phone:
        return ""
    if len(phone) <= 8:
        return phone
    return phone[:8] + "XXXXX"


@router.get("/stats")
async def stats(db: AsyncSession = Depends(get_db)):
    today = date.today()

    calls_today = (
        await db.execute(
            select(func.count()).select_from(CallLog).where(
                func.date(CallLog.created_at) == today
            )
        )
    ).scalar() or 0

    total_farmers = (
        await db.execute(select(func.count()).select_from(User))
    ).scalar() or 0

    avg_duration = (
        await db.execute(select(func.avg(CallLog.duration_seconds)))
    ).scalar()
    avg_duration_seconds = round(float(avg_duration), 1) if avg_duration else 0.0

    active_calls = (
        await db.execute(
            select(func.count()).select_from(CallLog).where(
                CallLog.status == "in-progress"
            )
        )
    ).scalar() or 0

    return {
        "calls_today": calls_today,
        "total_farmers": total_farmers,
        "avg_duration_seconds": avg_duration_seconds,
        "active_calls": active_calls,
    }


@router.get("/calls")
async def calls(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    language: str = Query("", description="Filter by language"),
    state: str = Query("", description="Filter by user state"),
    status: str = Query("", description="Filter by call status"),
    phone: str = Query("", description="Search by phone number"),
    db: AsyncSession = Depends(get_db),
):
    base = select(CallLog)
    count_q = select(func.count()).select_from(CallLog)

    if language:
        base = base.where(CallLog.language_detected == language)
        count_q = count_q.where(CallLog.language_detected == language)
    if status:
        base = base.where(CallLog.status == status)
        count_q = count_q.where(CallLog.status == status)
    if phone:
        base = base.where(CallLog.phone.contains(phone))
        count_q = count_q.where(CallLog.phone.contains(phone))
    if state:
        base = base.join(User, CallLog.phone == User.phone).where(User.state == state)
        count_q = count_q.join(User, CallLog.phone == User.phone).where(User.state == state)

    total = (await db.execute(count_q)).scalar() or 0

    query = base.order_by(CallLog.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    rows = result.scalars().all()

    # Lookup user state for each call
    phones = [r.phone for r in rows if r.phone]
    user_map = {}
    if phones:
        user_rows = (await db.execute(
            select(User).where(User.phone.in_(phones))
        )).scalars().all()
        user_map = {u.phone: u for u in user_rows}

    return {
        "calls": [
            {
                "call_sid": r.call_sid,
                "phone": _mask_phone(r.phone),
                "direction": r.direction,
                "status": r.status,
                "duration_seconds": r.duration_seconds,
                "language_detected": r.language_detected,
                "tools_used": r.tools_used,
                "state": user_map.get(r.phone, None) and user_map[r.phone].state or "",
                "district": user_map.get(r.phone, None) and user_map[r.phone].district or "",
                "created_at": str(r.created_at) if r.created_at else None,
                "ended_at": str(r.ended_at) if r.ended_at else None,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/calls/{call_sid}/transcript")
async def transcript(call_sid: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ConversationTurn)
        .where(ConversationTurn.call_sid == call_sid)
        .order_by(ConversationTurn.turn_number)
    )
    rows = result.scalars().all()
    return {
        "turns": [
            {
                "turn_number": r.turn_number,
                "speaker": r.speaker,
                "transcript": r.transcript,
                "tool_called": r.tool_called,
                "created_at": str(r.created_at) if r.created_at else None,
            }
            for r in rows
        ]
    }


@router.post("/calls/{call_sid}/end")
async def end_call(call_sid: str, db: AsyncSession = Depends(get_db)):
    """End an active call by deleting its LiveKit room."""
    log = await db.get(CallLog, call_sid)
    if not log:
        raise HTTPException(status_code=404, detail="Call not found")
    if log.status != "in-progress":
        raise HTTPException(status_code=400, detail="Call is not active")

    livekit_url = settings.livekit_url or "ws://localhost:7880"
    try:
        async with LiveKitAPI(
            url=livekit_url,
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
        ) as api:
            await api.room.delete_room(DeleteRoomRequest(room=call_sid))
        logger.info("Ended call (deleted room): %s", call_sid)
    except Exception:
        # Room may already be gone (server restart, etc.) — still mark completed
        logger.warning("LiveKit room %s not found or already closed", call_sid)

    # Always mark the call as completed in DB
    log.status = "completed"
    log.ended_at = func.now()
    await db.commit()

    return {"status": "ended", "call_sid": call_sid}


class TranslateRequest(BaseModel):
    texts: list[str]
    source_language: str  # e.g. "hi-IN"


# Map our language codes to AWS Translate codes
_LANG_TO_AWS = {
    "hi-IN": "hi", "ta-IN": "ta", "te-IN": "te", "kn-IN": "kn",
    "mr-IN": "mr", "bn-IN": "bn", "gu-IN": "gu", "pa-IN": "pa",
    "ml-IN": "ml", "od-IN": "or", "en-IN": "en",
}


@router.post("/translate")
async def translate(body: TranslateRequest):
    """Translate an array of texts to English using AWS Translate."""
    aws_lang = _LANG_TO_AWS.get(body.source_language, "auto")
    if aws_lang == "en":
        return {"translations": body.texts}

    import boto3
    client = boto3.client(
        "translate",
        region_name=settings.aws_default_region,
        aws_access_key_id=settings.aws_access_key_id or None,
        aws_secret_access_key=settings.aws_secret_access_key or None,
    )
    loop = asyncio.get_event_loop()

    async def _translate_one(text: str) -> str:
        if not text.strip():
            return text
        try:
            resp = await loop.run_in_executor(
                None,
                lambda t=text: client.translate_text(
                    Text=t[:5000],
                    SourceLanguageCode=aws_lang,
                    TargetLanguageCode="en",
                ),
            )
            return resp["TranslatedText"]
        except Exception:
            logger.exception("AWS Translate failed for text: %s", text[:50])
            return text

    translations = await asyncio.gather(*[_translate_one(t) for t in body.texts])
    return {"translations": list(translations)}


@router.get("/users")
async def users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    phone: str = Query("", description="Search by phone or name"),
    state: str = Query("", description="Filter by state"),
    crop: str = Query("", description="Filter by crop"),
    db: AsyncSession = Depends(get_db),
):
    base = select(User)
    count_q = select(func.count()).select_from(User)

    if phone:
        base = base.where(User.phone.contains(phone) | User.name.contains(phone))
        count_q = count_q.where(User.phone.contains(phone) | User.name.contains(phone))
    if state:
        base = base.where(User.state == state)
        count_q = count_q.where(User.state == state)
    if crop:
        base = base.where(User.crops.contains(crop))
        count_q = count_q.where(User.crops.contains(crop))

    total = (await db.execute(count_q)).scalar() or 0

    query = (
        base.order_by(User.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(query)
    rows = result.scalars().all()

    # Get call counts per user
    phones = [r.phone for r in rows]
    call_counts = {}
    if phones:
        cc_rows = (await db.execute(
            select(CallLog.phone, func.count().label("cnt"))
            .where(CallLog.phone.in_(phones))
            .group_by(CallLog.phone)
        )).all()
        call_counts = {r[0]: r[1] for r in cc_rows}

    return {
        "users": [
            {
                "phone": _mask_phone(r.phone),
                "name": r.name,
                "state": r.state,
                "district": r.district,
                "language": r.language,
                "crops": r.crops,
                "land_acres": r.land_acres,
                "call_count": call_counts.get(r.phone, 0),
                "created_at": str(r.created_at) if r.created_at else None,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/analytics")
async def analytics(db: AsyncSession = Depends(get_db)):
    today = date.today()
    month_start = today.replace(day=1)

    # Language distribution
    lang_rows = (
        await db.execute(
            select(CallLog.language_detected, func.count().label("count"))
            .where(CallLog.language_detected.is_not(None))
            .group_by(CallLog.language_detected)
            .order_by(func.count().desc())
        )
    ).all()

    language_distribution = [
        {"language": r[0], "count": r[1]} for r in lang_rows
    ]

    # Tool usage — explode comma-separated tools_used
    tool_rows = (
        await db.execute(
            select(CallLog.tools_used).where(CallLog.tools_used.is_not(None))
        )
    ).scalars().all()

    tool_counts: dict[str, int] = {}
    for tools_str in tool_rows:
        for tool in tools_str.split(","):
            tool = tool.strip()
            if tool:
                tool_counts[tool] = tool_counts.get(tool, 0) + 1

    tool_usage = sorted(
        [{"tool": t, "count": c} for t, c in tool_counts.items()],
        key=lambda x: x["count"],
        reverse=True,
    )

    # Call volume — last 7 days
    seven_days_ago = today - timedelta(days=6)
    vol_7d_rows = (
        await db.execute(
            select(
                cast(CallLog.created_at, Date).label("day"),
                func.count().label("calls"),
            )
            .where(func.date(CallLog.created_at) >= seven_days_ago)
            .group_by(cast(CallLog.created_at, Date))
            .order_by(cast(CallLog.created_at, Date))
        )
    ).all()
    call_volume_7d = [{"date": str(r[0]), "calls": r[1]} for r in vol_7d_rows]

    # Call volume — last 30 days
    thirty_days_ago = today - timedelta(days=29)
    vol_30d_rows = (
        await db.execute(
            select(
                cast(CallLog.created_at, Date).label("day"),
                func.count().label("calls"),
            )
            .where(func.date(CallLog.created_at) >= thirty_days_ago)
            .group_by(cast(CallLog.created_at, Date))
            .order_by(cast(CallLog.created_at, Date))
        )
    ).all()
    call_volume_30d = [{"date": str(r[0]), "calls": r[1]} for r in vol_30d_rows]

    # Total calls this month
    total_calls_month = (
        await db.execute(
            select(func.count()).select_from(CallLog)
            .where(func.date(CallLog.created_at) >= month_start)
        )
    ).scalar() or 0

    # Languages active count
    languages_active = (
        await db.execute(
            select(func.count(func.distinct(CallLog.language_detected)))
            .where(CallLog.language_detected.is_not(None))
        )
    ).scalar() or 0

    # New farmers this month
    new_farmers_month = (
        await db.execute(
            select(func.count()).select_from(User)
            .where(func.date(User.created_at) >= month_start)
        )
    ).scalar() or 0

    # Top commodities from tool usage (mandi queries)
    commodity_counts: dict[str, int] = {}
    # We can approximate from tools_used — for now just return tool usage as commodities
    # In future, parse actual query content from conversations

    # Top states by calls
    state_rows = (
        await db.execute(
            select(User.state, func.count().label("cnt"))
            .join(CallLog, User.phone == CallLog.phone)
            .where(User.state.is_not(None))
            .group_by(User.state)
            .order_by(func.count().desc())
            .limit(5)
        )
    ).all()
    top_states = [r[0] for r in state_rows]

    return {
        "language_distribution": language_distribution,
        "tool_usage": tool_usage,
        "call_volume_7d": call_volume_7d,
        "call_volume_30d": call_volume_30d,
        "total_calls_month": total_calls_month,
        "languages_active": languages_active,
        "new_farmers_month": new_farmers_month,
        "top_states": top_states,
    }
