import httpx
from dashboard.config import API_BASE


def get(path: str, params: dict | None = None) -> dict:
    try:
        resp = httpx.get(f"{API_BASE}{path}", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        return {"error": str(exc)}
