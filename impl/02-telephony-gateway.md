# Task 02: Telephony Gateway

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Handle Exotel missed calls, trigger outbound callbacks within 5 seconds, and manage WebSocket audio streams.

**Branch:** `feat/telephony`
**Worktree:** `../gramvaani-telephony`
**Depends On:** Task 01 (backend-foundation merged)

**Architecture:** Two webhook endpoints receive Exotel events. On missed call → log to DB → wait 5s → fire outbound call API. Exotel streams audio via WebSocket to `/ws/voice` where Pipecat pipeline takes over (Task 03).

---

## Setup

```bash
git checkout feat/backend-foundation
git pull
git checkout -b feat/telephony
```

---

### Step 1: Write failing tests

**Create `tests/test_webhooks.py`:**

```python
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock
from app.main import app

@pytest.mark.asyncio
async def test_missed_call_webhook_returns_200():
    payload = {
        "CallSid": "test-sid-001",
        "From": "+919876543210",
        "To": "+911234567890",
        "Status": "no-answer",
        "Direction": "inbound",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/webhooks/missed-call", data=payload)
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_missed_call_triggers_callback():
    payload = {"CallSid": "test-sid-002", "From": "+919876543210", "Status": "no-answer"}
    with patch("app.routers.webhooks.trigger_callback", new_callable=AsyncMock) as mock_cb:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/webhooks/missed-call", data=payload)
        mock_cb.assert_called_once_with("+919876543210")
```

**Run:** `pytest tests/test_webhooks.py -v`
Expected: FAIL — router not found yet.

---

### Step 2: Implement webhooks router

**Create `app/routers/webhooks.py`:**

```python
import asyncio
import httpx
from fastapi import APIRouter, Form, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.config import settings
from app.models.call_log import CallLog
from app.models.user import User

router = APIRouter(prefix="/webhooks", tags=["telephony"])

async def trigger_callback(phone: str):
    """Wait 5s then initiate outbound call via Exotel API."""
    await asyncio.sleep(5)
    url = f"https://api.exotel.com/v1/Accounts/{settings.exotel_account_sid}/Calls/connect"
    payload = {
        "From": phone,
        "To": settings.exotel_phone_number,
        "CallerId": settings.exotel_phone_number,
        "Url": "https://your-ngrok-url/ws/voice",  # replaced at deploy time
        "StatusCallback": "https://your-ngrok-url/webhooks/call-status",
    }
    auth = (settings.exotel_api_key, settings.exotel_api_token)
    async with httpx.AsyncClient() as client:
        await client.post(url, data=payload, auth=auth)

@router.post("/missed-call")
async def missed_call(
    background_tasks: BackgroundTasks,
    CallSid: str = Form(...),
    From: str = Form(...),
    To: str = Form(default=""),
    Status: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    # Ensure user record exists
    user = await db.get(User, From)
    if not user:
        user = User(phone=From)
        db.add(user)
        await db.commit()

    # Log the missed call
    log = CallLog(call_sid=CallSid, phone=From, direction="inbound", status="missed")
    db.add(log)
    await db.commit()

    # Trigger callback in background
    background_tasks.add_task(trigger_callback, From)
    return {"status": "callback_scheduled"}

@router.post("/call-status")
async def call_status(
    CallSid: str = Form(...),
    Status: str = Form(...),
    Duration: str = Form(default="0"),
    db: AsyncSession = Depends(get_db),
):
    log = await db.get(CallLog, CallSid)
    if log:
        log.status = Status
        log.duration_seconds = int(Duration) if Duration.isdigit() else 0
        await db.commit()
    return {"status": "updated"}
```

---

### Step 3: Register router in main.py

**Edit `app/main.py` — add after existing imports:**

```python
from app.routers import webhooks
app.include_router(webhooks.router)
```

---

### Step 4: Run tests — expect PASS

```bash
pytest tests/test_webhooks.py -v
```

Expected: 2 PASSED

---

### Step 5: Rate limiting via Redis

**Add to `app/routers/webhooks.py`:**

```python
from app.redis_client import cache_get, cache_set

async def is_rate_limited(phone: str) -> bool:
    """Prevent duplicate callbacks — 1 per phone per 60 seconds."""
    key = f"ratelimit:{phone}"
    if await cache_get(key):
        return True
    await cache_set(key, "1", ttl_seconds=60)
    return False
```

**Update `/missed-call` handler** — add before `trigger_callback`:

```python
if await is_rate_limited(From):
    return {"status": "rate_limited"}
```

---

### Step 6: Write rate limiting test

**Add to `tests/test_webhooks.py`:**

```python
@pytest.mark.asyncio
async def test_rate_limiting_prevents_duplicate_callback():
    payload = {"CallSid": "test-sid-003", "From": "+919999999999", "Status": "no-answer"}
    with patch("app.routers.webhooks.trigger_callback", new_callable=AsyncMock) as mock_cb:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/webhooks/missed-call", data=payload)
            await client.post("/webhooks/missed-call", data=payload)  # duplicate
        assert mock_cb.call_count == 1  # only first triggers callback
```

**Run:** `pytest tests/test_webhooks.py -v`
Expected: 3 PASSED

---

### Step 7: Commit

```bash
git add app/routers/webhooks.py tests/test_webhooks.py
git commit -m "feat: telephony gateway — missed call webhook, callback, rate limiting"
```

---

## Done when:
- [ ] `POST /webhooks/missed-call` logs call to DB and schedules callback
- [ ] Duplicate calls within 60s are rate-limited
- [ ] `POST /webhooks/call-status` updates call record
- [ ] All 3 tests pass
