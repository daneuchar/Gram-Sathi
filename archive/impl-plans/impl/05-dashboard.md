# Task 05: Streamlit Dashboard

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Build the 6-page Streamlit operator dashboard matching the approved wireframe.

**Branch:** `feat/dashboard`
**Worktree:** `../gramvaani-dashboard`
**Depends On:** Task 01 (backend-foundation merged — needs API endpoints)

**Architecture:** Streamlit multi-page app. Each page is a file in `dashboard/pages/`. Shared sidebar component. Data fetched from FastAPI `/api/dashboard/*` endpoints via httpx. Live Monitor uses polling (Streamlit doesn't support WebSocket natively — use `st.rerun()` every 3s).

**Wireframe reference:** `wireframes/` folder — see approved designs.

---

## Setup

```bash
git checkout feat/backend-foundation
git pull
git checkout -b feat/dashboard
mkdir -p dashboard/pages dashboard/components
touch dashboard/__init__.py dashboard/pages/__init__.py
```

---

### Step 1: Dashboard API endpoints in FastAPI

**Create `app/routers/dashboard.py`:**

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from app.database import get_db
from app.models.call_log import CallLog
from app.models.user import User
from app.models.conversation import ConversationTurn
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

@router.get("/health")
async def health():
    return {"status": "ok"}

@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Overview KPIs."""
    today = datetime.utcnow().date()
    calls_today = await db.scalar(
        select(func.count()).select_from(CallLog)
        .where(func.date(CallLog.created_at) == today)
    )
    total_farmers = await db.scalar(select(func.count()).select_from(User))
    avg_duration = await db.scalar(
        select(func.avg(CallLog.duration_seconds)).select_from(CallLog)
        .where(CallLog.duration_seconds != None)
    )
    return {
        "calls_today": calls_today or 0,
        "total_farmers": total_farmers or 0,
        "avg_duration_seconds": round(avg_duration or 0, 1),
        "active_calls": 0,  # updated via WebSocket in live monitor
    }

@router.get("/calls")
async def get_calls(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, le=100),
    language: str = Query(None),
    state: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Paginated call history."""
    q = select(CallLog).order_by(desc(CallLog.created_at))
    if language:
        q = q.where(CallLog.language_detected == language)
    offset = (page - 1) * per_page
    result = await db.execute(q.offset(offset).limit(per_page))
    calls = result.scalars().all()
    return {"calls": [
        {"call_sid": c.call_sid, "phone": c.phone[:8] + "XXXXX",
         "language": c.language_detected, "duration": c.duration_seconds,
         "status": c.status, "tools_used": c.tools_used,
         "created_at": c.created_at.isoformat() if c.created_at else None}
        for c in calls
    ], "page": page, "per_page": per_page}

@router.get("/users")
async def get_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Paginated farmer profiles."""
    q = select(User).order_by(desc(User.created_at))
    offset = (page - 1) * per_page
    result = await db.execute(q.offset(offset).limit(per_page))
    users = result.scalars().all()
    return {"users": [
        {"phone": u.phone[:8] + "XXXXX", "name": u.name or "(Unknown)",
         "state": u.state, "crops": u.crops, "language": u.language,
         "land_acres": u.land_acres}
        for u in users
    ], "page": page, "per_page": per_page}

@router.get("/analytics")
async def get_analytics(db: AsyncSession = Depends(get_db)):
    """Aggregated analytics data."""
    lang_dist = await db.execute(
        select(CallLog.language_detected, func.count().label("count"))
        .group_by(CallLog.language_detected)
        .order_by(desc("count"))
    )
    tools_dist = await db.execute(
        select(ConversationTurn.tool_called, func.count().label("count"))
        .where(ConversationTurn.tool_called != None)
        .group_by(ConversationTurn.tool_called)
        .order_by(desc("count"))
    )
    return {
        "language_distribution": [{"language": r[0], "count": r[1]} for r in lang_dist],
        "tool_usage": [{"tool": r[0], "count": r[1]} for r in tools_dist],
    }
```

**Register in `app/main.py`:**

```python
from app.routers import dashboard
app.include_router(dashboard.router)
```

---

### Step 2: Dashboard config & API client

**Create `dashboard/config.py`:**

```python
API_BASE = "http://localhost:8000"
POLL_INTERVAL_SECONDS = 3

COLORS = {
    "primary": "#1E40AF",
    "success": "#16A34A",
    "warning": "#D97706",
    "danger": "#DC2626",
    "bg": "#F8F9FA",
}
```

**Create `dashboard/api.py`:**

```python
import httpx
from dashboard.config import API_BASE

def get(path: str, params: dict = None) -> dict:
    """Synchronous API call for Streamlit."""
    try:
        with httpx.Client(base_url=API_BASE, timeout=5.0) as client:
            resp = client.get(path, params=params)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        return {"error": str(e)}
```

---

### Step 3: Main app entry point

**Create `dashboard/app.py`:**

```python
import streamlit as st

st.set_page_config(
    page_title="Gram Saathi",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Sidebar navigation
with st.sidebar:
    st.markdown("### 🌾 Gram Saathi")
    st.markdown("---")
    page = st.radio(
        "Navigate",
        ["📊 Overview", "🔴 Live Monitor", "📋 Call History",
         "👤 User Profiles", "📈 Analytics", "⚙️ System Health"],
        label_visibility="hidden",
    )

# Route to page
if "Overview" in page:
    from dashboard.pages import overview; overview.render()
elif "Live Monitor" in page:
    from dashboard.pages import live_monitor; live_monitor.render()
elif "Call History" in page:
    from dashboard.pages import call_history; call_history.render()
elif "User Profiles" in page:
    from dashboard.pages import user_profiles; user_profiles.render()
elif "Analytics" in page:
    from dashboard.pages import analytics; analytics.render()
elif "System Health" in page:
    from dashboard.pages import system_health; system_health.render()
```

---

### Step 4: Overview page

**Create `dashboard/pages/overview.py`:**

```python
import streamlit as st
import pandas as pd
from dashboard.api import get

def render():
    st.title("Dashboard Overview")

    col1, col2, col3, col4 = st.columns(4)
    stats = get("/api/dashboard/stats")

    with col1:
        st.metric("Active Calls", stats.get("active_calls", 0), delta="Live")
    with col2:
        st.metric("Calls Today", stats.get("calls_today", 0))
    with col3:
        st.metric("Farmers Served", f"{stats.get('total_farmers', 0):,}")
    with col4:
        avg = stats.get("avg_duration_seconds", 0)
        m, s = divmod(int(avg), 60)
        st.metric("Avg Duration", f"{m}m {s}s")

    st.markdown("---")

    col_left, col_right = st.columns([3, 2])
    with col_left:
        st.subheader("Call Volume — Last 7 Days")
        st.info("Chart placeholder — connect time-series data from /api/dashboard/calls")

    with col_right:
        st.subheader("Query Type Breakdown")
        analytics = get("/api/dashboard/analytics")
        tool_data = analytics.get("tool_usage", [])
        if tool_data:
            df = pd.DataFrame(tool_data)
            st.bar_chart(df.set_index("tool")["count"])
        else:
            st.info("No tool usage data yet")

    st.markdown("---")
    st.subheader("Alerts & Issues")
    st.warning("⚠️ Connect to system health endpoint to show live alerts")
```

---

### Step 5: Live Monitor page

**Create `dashboard/pages/live_monitor.py`:**

```python
import streamlit as st
import time
from dashboard.api import get
from dashboard.config import POLL_INTERVAL_SECONDS

def render():
    st.title("Live Monitor")
    st.caption("Auto-refreshes every 3 seconds via polling")

    placeholder = st.empty()

    # Active calls (polled from API)
    active = get("/api/dashboard/calls")
    calls = [c for c in active.get("calls", []) if c.get("status") == "in-progress"]

    with placeholder.container():
        if not calls:
            st.info("No active calls right now — waiting for new connections...")
        for call in calls:
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([3, 1, 1, 2])
                c1.markdown(f"**{call['phone']}**")
                c2.markdown(call.get("language", "—"))
                c3.markdown(f"🟢 Live")
                c4.markdown(call.get("created_at", "")[:19])

    time.sleep(POLL_INTERVAL_SECONDS)
    st.rerun()
```

---

### Step 6: Call History page

**Create `dashboard/pages/call_history.py`:**

```python
import streamlit as st
import pandas as pd
from dashboard.api import get

def render():
    st.title("Call History")

    col1, col2, col3 = st.columns(3)
    with col1:
        lang_filter = st.selectbox("Language", ["All", "Hindi", "Tamil", "Telugu", "Marathi"])
    with col2:
        state_filter = st.selectbox("State", ["All", "UP", "TN", "AP", "MH", "RJ"])
    with col3:
        page = st.number_input("Page", min_value=1, value=1)

    params = {"page": page, "per_page": 20}
    if lang_filter != "All":
        params["language"] = lang_filter

    data = get("/api/dashboard/calls", params=params)
    calls = data.get("calls", [])

    if calls:
        df = pd.DataFrame(calls)
        df = df[["phone", "language", "duration", "status", "tools_used", "created_at"]]
        df.columns = ["Phone", "Language", "Duration (s)", "Status", "Tools Used", "Time"]
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No calls found")
```

---

### Step 7: User Profiles, Analytics, System Health pages

**Create `dashboard/pages/user_profiles.py`:**

```python
import streamlit as st
import pandas as pd
from dashboard.api import get

def render():
    st.title("User Profiles")
    page = st.number_input("Page", min_value=1, value=1)
    data = get("/api/dashboard/users", params={"page": page})
    users = data.get("users", [])
    if users:
        df = pd.DataFrame(users)[["phone", "name", "state", "crops", "language", "land_acres"]]
        df.columns = ["Phone", "Name", "State", "Crops", "Language", "Land (acres)"]
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No farmers yet")
```

**Create `dashboard/pages/analytics.py`:**

```python
import streamlit as st
import pandas as pd
from dashboard.api import get

def render():
    st.title("Analytics")
    data = get("/api/dashboard/analytics")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Language Distribution")
        lang_data = data.get("language_distribution", [])
        if lang_data:
            df = pd.DataFrame(lang_data)
            st.bar_chart(df.set_index("language")["count"])

    with col2:
        st.subheader("Tool Usage Breakdown")
        tool_data = data.get("tool_usage", [])
        if tool_data:
            df = pd.DataFrame(tool_data)
            st.bar_chart(df.set_index("tool")["count"])
```

**Create `dashboard/pages/system_health.py`:**

```python
import streamlit as st
from dashboard.api import get

SERVICES = [
    ("FastAPI Backend", "/api/health"),
]

def render():
    st.title("System Health")
    st.caption("Manual refresh — click button below")
    if st.button("↻ Refresh"):
        st.rerun()

    for name, path in SERVICES:
        result = get(path)
        if "error" in result:
            st.error(f"🔴 {name} — DOWN: {result['error']}")
        else:
            st.success(f"🟢 {name} — Healthy")

    st.markdown("---")
    st.subheader("Cache & Latency")
    st.info("Connect Redis and latency monitoring in production")
```

---

### Step 8: Dockerfile for dashboard

**Create `Dockerfile.dashboard`:**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir streamlit httpx pandas
COPY dashboard/ ./dashboard/
CMD ["streamlit", "run", "dashboard/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

---

### Step 9: Run locally

```bash
cd /Users/danieleuchar/workspace/gramvaani
streamlit run dashboard/app.py
```

Expected: Dashboard opens at `http://localhost:8501`

---

### Step 10: Commit

```bash
git add dashboard/ app/routers/dashboard.py Dockerfile.dashboard
git commit -m "feat: streamlit dashboard — all 6 pages (overview, live, history, profiles, analytics, health)"
```

---

## Done when:
- [ ] `streamlit run dashboard/app.py` opens without errors
- [ ] Overview page shows KPI cards
- [ ] Call History table loads from API
- [ ] All 6 pages render without exceptions
