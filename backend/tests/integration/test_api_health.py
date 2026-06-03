"""Integration tests for health check and basic API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    """Test the /health endpoint returns valid response."""
    response = await client.get("/health")
    assert response.status_code in (200, 503)
    data = response.json()
    assert "status" in data
    assert data["status"] in ("ok", "degraded")


@pytest.mark.asyncio
async def test_health_live_endpoint(client: AsyncClient):
    """Test the /health/live liveness probe."""
    response = await client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"


@pytest.mark.asyncio
async def test_health_ready_endpoint(client: AsyncClient):
    """Test the /health/ready readiness probe."""
    response = await client.get("/health/ready")
    assert response.status_code in (200, 503)
    data = response.json()
    assert "status" in data
    assert data["status"] in ("ready", "not_ready")


@pytest.mark.asyncio
async def test_ping_endpoint(client: AsyncClient):
    """Test the /api/v1/ping endpoint."""
    response = await client.get("/api/v1/ping")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "edition" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_metrics_endpoint(client: AsyncClient):
    """Test the /metrics Prometheus endpoint."""
    response = await client.get("/metrics")
    assert response.status_code == 200
    text = response.text
    assert "HELP" in text or "#" in text  # Prometheus format
