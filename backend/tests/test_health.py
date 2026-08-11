import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check_ok(plain_client: AsyncClient):
    resp = await plain_client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["config_loaded"] is True
    assert body["service"] == "metroguardian-backend"
