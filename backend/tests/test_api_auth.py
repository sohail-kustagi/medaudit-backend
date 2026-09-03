import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_auth_guard_rejects_missing_token(client: AsyncClient):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert "Authorization token missing" in response.json()["detail"]


@pytest.mark.asyncio
async def test_auth_accepts_valid_token_and_provisions_user(client: AsyncClient):
    headers = {"Authorization": "Bearer mock-user-sub-12345"}
    response = await client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["cognito_sub"] == "mock-user-sub-12345"
    assert "mock-user-sub-12345@example.com" in data["email"]
    assert data["id"] is not None
