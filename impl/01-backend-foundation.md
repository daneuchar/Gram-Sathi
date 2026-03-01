# Task 01: Backend Foundation

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Scaffold the FastAPI application, define the database schema, set up in-memory cache, and get Docker Compose running locally.

**Branch:** `feat/backend-foundation`
**Worktree:** `../gramvaani-backend`
**Blocks:** All other tasks (02–06)

**Architecture:** Single FastAPI app with separate routers per domain. PostgreSQL via SQLAlchemy async. In-memory TTL cache via `cachetools` (no Redis for prototype — swap-in ready for production). All config via environment variables.

**Tech Stack:** Python 3.11, FastAPI 0.110, SQLAlchemy 2.0 (async), Alembic, asyncpg, cachetools, pydantic-settings, Docker Compose

---

## Setup

```bash
cd /Users/danieleuchar/workspace/gramvaani
git init && git add . && git commit -m "chore: initial commit"
git checkout -b feat/backend-foundation
```

---

### Step 1: Project Structure

**Create the following directory tree:**

```
gramvaani/
├── app/
│   ├── __init__.py
│   ├── main.py               # FastAPI app entry point
│   ├── config.py             # Pydantic settings
│   ├── database.py           # SQLAlchemy async engine + session
│   ├── cache.py              # In-memory TTL cache (cachetools)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── call_log.py
│   │   ├── conversation.py
│   │   └── alert.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── webhooks.py       # Exotel webhooks (Task 02)
│   │   ├── voice.py          # WebSocket voice (Task 03)
│   │   └── dashboard.py      # Dashboard API (Task 05)
│   └── schemas/
│       ├── __init__.py
│       ├── user.py
│       └── call_log.py
├── alembic/
│   └── versions/
├── tests/
│   ├── __init__.py
│   ├── test_health.py
│   └── test_models.py
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env.example
```

**Run:**
```bash
mkdir -p app/{models,routers,schemas} alembic/versions tests
touch app/__init__.py app/models/__init__.py app/routers/__init__.py app/schemas/__init__.py tests/__init__.py
```

---

### Step 2: requirements.txt

**Create `requirements.txt`:**

```text
fastapi==0.110.0
uvicorn[standard]==0.27.1
sqlalchemy[asyncio]==2.0.28
asyncpg==0.29.0
alembic==1.13.1
cachetools==5.3.3
pydantic-settings==2.2.1
python-dotenv==1.0.1
httpx==0.27.0
websockets==12.0
pipecat-ai==0.0.45
boto3==1.34.0
pytest==8.1.0
pytest-asyncio==0.23.5
pytest-httpx==0.30.0
streamlit==1.32.0
```

---

### Step 3: config.py

**Create `app/config.py`:**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # AWS Bedrock
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_default_region: str = "ap-south-1"
    bedrock_model_id: str = "amazon.nova-lite-v1:0"  # Lite = ~3x faster; upgrade to nova-pro-v1:0 if quality issues

    # Sarvam
    sarvam_api_key: str

    # Exotel
    exotel_api_key: str
    exotel_api_token: str
    exotel_account_sid: str
    exotel_phone_number: str

    # External APIs
    data_gov_api_key: str = ""
    indian_api_key: str

    # Amazon Q Business
    amazon_q_app_id: str = ""
    amazon_q_index_id: str = ""

    # Database
    database_url: str = "postgresql+asyncpg://gramvaani:gramvaani@localhost:5432/gramvaani"

    # App
    debug: bool = False

    class Config:
        env_file = ".env"

settings = Settings()
```

---

### Step 4: docker-compose.yml

**Create `docker-compose.yml`:**

```yaml
version: "3.9"
services:
  backend:
    build: .
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - ./app:/app/app

  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: gramvaani
      POSTGRES_PASSWORD: gramvaani
      POSTGRES_DB: gramvaani
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U gramvaani"]
      interval: 5s
      timeout: 5s
      retries: 5

  dashboard:
    build:
      context: .
      dockerfile: Dockerfile.dashboard
    ports:
      - "8501:8501"
    env_file: .env
    depends_on:
      - backend

# NOTE: Redis intentionally omitted for prototype.
# Using cachetools in-memory TTL cache instead.
# To add Redis for production: add redis service here
# and swap cache.py for redis_client.py (same interface).
```

---

### Step 5: Dockerfile

**Create `Dockerfile`:**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

---

### Step 6: Database Models

**Create `app/models/user.py`:**

```python
from sqlalchemy import Column, String, Float, DateTime, func
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    phone = Column(String(20), primary_key=True)
    name = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    language = Column(String(50), nullable=True)
    crops = Column(String(500), nullable=True)        # comma-separated
    land_acres = Column(Float, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
```

**Create `app/models/call_log.py`:**

```python
from sqlalchemy import Column, String, Integer, DateTime, func, ForeignKey
from app.models.user import Base

class CallLog(Base):
    __tablename__ = "call_logs"

    call_sid = Column(String(100), primary_key=True)
    phone = Column(String(20), ForeignKey("users.phone"))
    direction = Column(String(20))     # inbound | outbound
    status = Column(String(30))        # completed | failed | busy
    duration_seconds = Column(Integer, nullable=True)
    language_detected = Column(String(50), nullable=True)
    tools_used = Column(String(500), nullable=True)   # comma-separated
    created_at = Column(DateTime, server_default=func.now())
    ended_at = Column(DateTime, nullable=True)
```

**Create `app/models/conversation.py`:**

```python
from sqlalchemy import Column, String, Integer, Float, DateTime, func, ForeignKey
from app.models.user import Base

class ConversationTurn(Base):
    __tablename__ = "conversation_turns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    call_sid = Column(String(100), ForeignKey("call_logs.call_sid"))
    turn_number = Column(Integer)
    speaker = Column(String(10))       # user | assistant
    transcript = Column(String(2000))
    tool_called = Column(String(100), nullable=True)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
```

---

### Step 7: database.py

**Create `app/database.py`:**

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings
from app.models.user import Base

engine = create_async_engine(settings.database_url, echo=settings.debug)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
```

---

### Step 8: cache.py (in-memory TTL cache — no Redis)

**Create `app/cache.py`:**

```python
from cachetools import TTLCache

# Shared in-memory caches with TTL
# maxsize: max entries before LRU eviction
_api_cache = TTLCache(maxsize=1000, ttl=1800)   # 30-min default (mandi prices)
_rate_limit_cache = TTLCache(maxsize=500, ttl=60)  # 60-sec (duplicate callback prevention)

def cache_get(key: str):
    return _api_cache.get(key)

def cache_set(key: str, value: str, ttl_seconds: int = 1800):
    # cachetools TTLCache uses a single TTL per cache instance.
    # For different TTLs, use a separate cache or store (value, expiry) tuple.
    _api_cache[key] = value

def is_rate_limited(key: str) -> bool:
    """Returns True if key was seen in last 60 seconds."""
    if key in _rate_limit_cache:
        return True
    _rate_limit_cache[key] = 1
    return False

# NOTE: These functions are synchronous (no await needed).
# Drop-in replacement for Redis: just add async/await + Redis client when scaling up.
```

> **Production swap:** Replace `cache.py` with an async Redis client — the interface (`cache_get`, `cache_set`, `is_rate_limited`) stays identical. All callers require zero changes.

---

### Step 9: main.py

**Create `app/main.py`:**

```python
from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.database import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(title="Gram Saathi API", version="1.0.0", lifespan=lifespan)

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "gram-saathi"}

# Routers added in later tasks
```

---

### Step 10: Write & run tests

**Create `tests/test_health.py`:**

```python
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
```

**Run:**
```bash
docker compose up postgres -d
pip install -r requirements.txt
pytest tests/test_health.py -v
```

Expected: `PASSED`

---

### Step 11: Commit

```bash
git add .
git commit -m "feat: backend foundation — FastAPI, models, DB, in-memory cache, Docker"
```

---

## Done when:
- [ ] `docker compose up` starts postgres + backend without errors (no Redis)
- [ ] `GET /api/health` returns `{"status": "ok"}`
- [ ] `pytest tests/test_health.py` passes
- [ ] All model tables created in postgres
- [ ] `cache.py` imported and working (no external dependency)
