from unittest.mock import AsyncMock, MagicMock, patch

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
def _clear_rate_limit():
    """Clear the rate-limit cache so tests are isolated."""
    from app.cache import _rate_limit_cache
    _rate_limit_cache.clear()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.usefixtures("_clear_rate_limit")
async def test_missed_call_webhook_returns_200(client: AsyncClient):
    resp = await client.post(
        "/webhooks/missed-call",
        data={"CallSid": "sid-001", "From": "+919999900001", "Status": "missed"},
    )
    assert resp.status_code == 200


@pytest.mark.usefixtures("_clear_rate_limit")
async def test_missed_call_triggers_callback(client: AsyncClient):
    with patch("app.routers.webhooks.trigger_callback") as mock_cb:
        resp = await client.post(
            "/webhooks/missed-call",
            data={"CallSid": "sid-002", "From": "+919999900002", "Status": "missed"},
        )
        assert resp.status_code == 200
        mock_cb.assert_called_once_with("+919999900002")


@pytest.mark.usefixtures("_clear_rate_limit")
async def test_rate_limiting_prevents_duplicate(client: AsyncClient):
    with patch("app.routers.webhooks.trigger_callback") as mock_cb:
        await client.post(
            "/webhooks/missed-call",
            data={"CallSid": "sid-003a", "From": "+919999900003", "Status": "missed"},
        )
        await client.post(
            "/webhooks/missed-call",
            data={"CallSid": "sid-003b", "From": "+919999900003", "Status": "missed"},
        )
        mock_cb.assert_called_once()
