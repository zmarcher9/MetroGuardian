import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from tests.conftest import csrf_headers

pytestmark = pytest.mark.db

settings = get_settings()


async def _prime_csrf(client: AsyncClient) -> None:
    await client.get("/api/v1/auth/me")


async def _signup(client: AsyncClient, email: str) -> None:
    await _prime_csrf(client)
    resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "password1"},
        headers=csrf_headers(client),
    )
    assert resp.status_code == 200


def _route_payload(name: str = "Home to Work") -> dict:
    return {
        "name": name,
        "origin": {"lat": 40.0, "lng": -75.0},
        "dest": {"lat": 40.1, "lng": -75.1},
    }


# ---------------------------------------------------------------------------
# auth requirement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthenticated_crud_is_rejected(client: AsyncClient):
    assert (await client.get("/api/v1/saved-routes")).status_code == 401
    assert (await client.get("/api/v1/saved-routes/00000000-0000-0000-0000-000000000000")).status_code == 401
    await _prime_csrf(client)
    create_resp = await client.post(
        "/api/v1/saved-routes", json=_route_payload(), headers=csrf_headers(client)
    )
    assert create_resp.status_code == 401
    delete_resp = await client.delete(
        "/api/v1/saved-routes/00000000-0000-0000-0000-000000000000", headers=csrf_headers(client)
    )
    assert delete_resp.status_code == 401


# ---------------------------------------------------------------------------
# create / get / list happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_list_returns_own_route(client: AsyncClient):
    await _signup(client, "saved-routes-create@example.com")
    resp = await client.post(
        "/api/v1/saved-routes", json=_route_payload(), headers=csrf_headers(client)
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Home to Work"
    assert body["origin"] == {"lat": 40.0, "lng": -75.0}
    assert body["dest"] == {"lat": 40.1, "lng": -75.1}
    assert body["waypoints"] is None

    list_resp = await client.get("/api/v1/saved-routes")
    assert list_resp.status_code == 200
    ids = [r["id"] for r in list_resp.json()]
    assert body["id"] in ids


@pytest.mark.asyncio
async def test_get_own_route_by_id_returns_full_match(client: AsyncClient):
    await _signup(client, "saved-routes-get@example.com")
    create_resp = await client.post(
        "/api/v1/saved-routes", json=_route_payload("Owned Route"), headers=csrf_headers(client)
    )
    created = create_resp.json()

    get_resp = await client.get(f"/api/v1/saved-routes/{created['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json() == created


@pytest.mark.asyncio
async def test_list_orders_newest_first(client: AsyncClient):
    await _signup(client, "saved-routes-order@example.com")
    first = (
        await client.post("/api/v1/saved-routes", json=_route_payload("First"), headers=csrf_headers(client))
    ).json()
    second = (
        await client.post("/api/v1/saved-routes", json=_route_payload("Second"), headers=csrf_headers(client))
    ).json()

    list_resp = await client.get("/api/v1/saved-routes")
    ids = [r["id"] for r in list_resp.json()]
    assert ids.index(second["id"]) < ids.index(first["id"])


@pytest.mark.asyncio
async def test_waypoints_round_trip(client: AsyncClient):
    await _signup(client, "saved-routes-waypoints@example.com")
    payload = _route_payload("With waypoints")
    payload["waypoints"] = [{"lat": 40.05, "lng": -75.05}, {"lat": 40.08, "lng": -75.08}]

    resp = await client.post("/api/v1/saved-routes", json=payload, headers=csrf_headers(client))
    assert resp.status_code == 201
    assert resp.json()["waypoints"] == payload["waypoints"]

    get_resp = await client.get(f"/api/v1/saved-routes/{resp.json()['id']}")
    assert get_resp.json()["waypoints"] == payload["waypoints"]


# ---------------------------------------------------------------------------
# limit boundaries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_limit_truncates_and_rejects_out_of_range(client: AsyncClient):
    await _signup(client, "saved-routes-limit@example.com")
    for i in range(3):
        await client.post(
            "/api/v1/saved-routes", json=_route_payload(f"Route {i}"), headers=csrf_headers(client)
        )

    truncated = await client.get("/api/v1/saved-routes", params={"limit": 2})
    assert truncated.status_code == 200
    # Not just a count check - confirms limit is applied *after* newest-first
    # ordering (the 2 most recently created), not an arbitrary 2 of 3.
    assert [r["name"] for r in truncated.json()] == ["Route 2", "Route 1"]

    assert (await client.get("/api/v1/saved-routes", params={"limit": 0})).status_code == 422
    assert (await client.get("/api/v1/saved-routes", params={"limit": 501})).status_code == 422


# ---------------------------------------------------------------------------
# per-user cap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_rejects_past_per_user_cap(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "saved_routes_max_per_user", 2)
    await _signup(client, "saved-routes-cap@example.com")

    for i in range(2):
        resp = await client.post(
            "/api/v1/saved-routes", json=_route_payload(f"Cap {i}"), headers=csrf_headers(client)
        )
        assert resp.status_code == 201

    over_cap = await client.post(
        "/api/v1/saved-routes", json=_route_payload("Over cap"), headers=csrf_headers(client)
    )
    assert over_cap.status_code == 422


@pytest.mark.asyncio
async def test_per_user_cap_is_independent_per_user(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "saved_routes_max_per_user", 1)

    await _signup(client, "saved-routes-cap-a@example.com")
    assert (
        await client.post("/api/v1/saved-routes", json=_route_payload("A1"), headers=csrf_headers(client))
    ).status_code == 201
    assert (
        await client.post("/api/v1/saved-routes", json=_route_payload("A2"), headers=csrf_headers(client))
    ).status_code == 422

    await _signup(client, "saved-routes-cap-b@example.com")
    # User B is unaffected by user A already being at the cap.
    assert (
        await client.post("/api/v1/saved-routes", json=_route_payload("B1"), headers=csrf_headers(client))
    ).status_code == 201


# ---------------------------------------------------------------------------
# cross-user isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_user_get_and_delete_are_404(client: AsyncClient):
    await _signup(client, "saved-routes-user-a@example.com")
    created = (
        await client.post(
            "/api/v1/saved-routes", json=_route_payload("User A's route"), headers=csrf_headers(client)
        )
    ).json()

    await _signup(client, "saved-routes-user-b@example.com")

    get_resp = await client.get(f"/api/v1/saved-routes/{created['id']}")
    assert get_resp.status_code == 404

    delete_resp = await client.delete(
        f"/api/v1/saved-routes/{created['id']}", headers=csrf_headers(client)
    )
    assert delete_resp.status_code == 404


@pytest.mark.asyncio
async def test_list_is_scoped_per_user_with_multiple_rows_each(client: AsyncClient):
    await _signup(client, "saved-routes-multi-a@example.com")
    a_ids = set()
    for i in range(2):
        resp = await client.post(
            "/api/v1/saved-routes", json=_route_payload(f"A {i}"), headers=csrf_headers(client)
        )
        a_ids.add(resp.json()["id"])

    await _signup(client, "saved-routes-multi-b@example.com")
    for i in range(2):
        await client.post(
            "/api/v1/saved-routes", json=_route_payload(f"B {i}"), headers=csrf_headers(client)
        )

    # Switch back to user A by logging in again (same client/cookie jar).
    await client.post(
        "/api/v1/auth/login",
        json={"email": "saved-routes-multi-a@example.com", "password": "password1"},
        headers=csrf_headers(client),
    )
    list_resp = await client.get("/api/v1/saved-routes")
    returned_ids = {r["id"] for r in list_resp.json()}
    assert returned_ids == a_ids


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_removes_route_from_subsequent_list(client: AsyncClient):
    await _signup(client, "saved-routes-delete@example.com")
    created = (
        await client.post(
            "/api/v1/saved-routes", json=_route_payload("To delete"), headers=csrf_headers(client)
        )
    ).json()

    delete_resp = await client.delete(
        f"/api/v1/saved-routes/{created['id']}", headers=csrf_headers(client)
    )
    assert delete_resp.status_code == 204

    list_resp = await client.get("/api/v1/saved-routes")
    ids = [r["id"] for r in list_resp.json()]
    assert created["id"] not in ids


@pytest.mark.asyncio
async def test_double_delete_is_idempotent_second_call_404s(client: AsyncClient):
    await _signup(client, "saved-routes-double-delete@example.com")
    created = (
        await client.post(
            "/api/v1/saved-routes", json=_route_payload("Delete twice"), headers=csrf_headers(client)
        )
    ).json()

    first = await client.delete(f"/api/v1/saved-routes/{created['id']}", headers=csrf_headers(client))
    assert first.status_code == 204
    second = await client.delete(f"/api/v1/saved-routes/{created['id']}", headers=csrf_headers(client))
    assert second.status_code == 404


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_delete_without_csrf_header_are_rejected(client: AsyncClient):
    await _signup(client, "saved-routes-csrf@example.com")

    create_resp = await client.post("/api/v1/saved-routes", json=_route_payload())
    assert create_resp.status_code == 403

    created = (
        await client.post("/api/v1/saved-routes", json=_route_payload(), headers=csrf_headers(client))
    ).json()
    delete_resp = await client.delete(f"/api/v1/saved-routes/{created['id']}")
    assert delete_resp.status_code == 403


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_rejects_empty_name(client: AsyncClient):
    await _signup(client, "saved-routes-empty-name@example.com")
    payload = _route_payload("")
    resp = await client.post("/api/v1/saved-routes", json=payload, headers=csrf_headers(client))
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_rejects_out_of_range_lat_lng(client: AsyncClient):
    await _signup(client, "saved-routes-bad-latlng@example.com")
    payload = _route_payload()
    payload["origin"]["lat"] = 999
    resp = await client.post("/api/v1/saved-routes", json=payload, headers=csrf_headers(client))
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_non_uuid_id_returns_422(client: AsyncClient):
    await _signup(client, "saved-routes-non-uuid@example.com")
    resp = await client.get("/api/v1/saved-routes/not-a-uuid")
    assert resp.status_code == 422
