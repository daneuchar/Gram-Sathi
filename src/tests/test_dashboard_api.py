import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.database import get_db
from app.models.base import Base

# In-memory SQLite for testing
test_engine = create_async_engine("sqlite+aiosqlite:///", echo=False)
TestSession = async_sessionmaker(test_engine, expire_on_commit=False)


async def override_get_db():
    async with TestSession() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_stats_endpoint_returns_valid_structure(client):
    resp = await client.get("/api/dashboard/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "calls_today" in data
    assert "total_farmers" in data
    assert "avg_duration_seconds" in data
    assert "active_calls" in data


@pytest.mark.asyncio
async def test_calls_endpoint_paginated(client):
    resp = await client.get("/api/dashboard/calls")
    assert resp.status_code == 200
    data = resp.json()
    assert "calls" in data
    assert isinstance(data["calls"], list)
    assert "page" in data
    assert "per_page" in data
