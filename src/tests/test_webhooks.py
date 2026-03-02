from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.database import get_db


# Stub DB session for all tests
@pytest.fixture(autouse=True)
def _override_db():
    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=None)
    mock_session.add = MagicMock()  # session.add() is sync in SQLAlchemy

    async def _fake_db():
        yield mock_session

    app.dependency_overrides[get_db] = _fake_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_inbound_call_returns_twiml(client: AsyncClient):
    resp = await client.post(
        "/webhooks/inbound-call",
        data={"CallSid": "CA123", "From": "+919999900001"},
    )
    assert resp.status_code == 200
    assert "telephone/handler" in resp.text


async def test_call_status_returns_ok(client: AsyncClient):
    resp = await client.post(
        "/webhooks/call-status",
        data={"CallSid": "CA123", "CallStatus": "completed", "CallDuration": "30"},
    )
    assert resp.status_code == 200
