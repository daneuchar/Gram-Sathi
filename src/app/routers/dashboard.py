from datetime import date
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.call_log import CallLog
from app.models.user import User

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
    db: AsyncSession = Depends(get_db),
):
    query = select(CallLog)

    if language:
        query = query.where(CallLog.language_detected == language)
    if status:
        query = query.where(CallLog.status == status)
    if state:
        query = query.join(User, CallLog.phone == User.phone).where(User.state == state)

    query = query.order_by(CallLog.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    rows = result.scalars().all()

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
                "created_at": str(r.created_at) if r.created_at else None,
                "ended_at": str(r.ended_at) if r.ended_at else None,
            }
            for r in rows
        ],
        "page": page,
        "per_page": per_page,
    }


@router.get("/users")
async def users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(User)
        .order_by(User.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(query)
    rows = result.scalars().all()

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
                "created_at": str(r.created_at) if r.created_at else None,
            }
            for r in rows
        ],
        "page": page,
        "per_page": per_page,
    }


@router.get("/analytics")
async def analytics(db: AsyncSession = Depends(get_db)):
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

    return {
        "language_distribution": language_distribution,
        "tool_usage": tool_usage,
    }
