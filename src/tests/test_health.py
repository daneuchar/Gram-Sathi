import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "gram-saathi"


def test_cache_get_set():
    from app.cache import cache_get, cache_set
    cache_set("test:key", "hello")
    assert cache_get("test:key") == "hello"
    assert cache_get("test:missing") is None


def test_rate_limiting():
    from app.cache import is_rate_limited
    assert is_rate_limited("phone:+919999000001") is False   # first call — not limited
    assert is_rate_limited("phone:+919999000001") is True    # second call — limited
    assert is_rate_limited("phone:+919999000002") is False   # different phone — not limited
