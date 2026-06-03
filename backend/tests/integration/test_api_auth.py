"""Integration tests for authentication API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_missing_fields(client: AsyncClient):
    """Test login with missing fields returns 422."""
    response = await client.post("/api/v1/login", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient):
    """Test login with invalid credentials returns 401."""
    response = await client.post("/api/v1/login", json={
        "username": "nonexistent_user",
        "password": "wrong_password",
    })
    assert response.status_code in (401, 403, 422)


@pytest.mark.asyncio
async def test_protected_endpoint_without_token(client: AsyncClient):
    """Test that protected endpoints require authentication."""
    response = await client.get("/api/v1/users/me")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_protected_endpoint_with_invalid_token(client: AsyncClient):
    """Test that invalid tokens are rejected."""
    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Bearer invalid_token_here"}
    )
    assert response.status_code in (401, 403)
