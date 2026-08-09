import sys
import os
import asyncio
import tempfile
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

os.environ.setdefault("DATABASE_TYPE", "sqlite")
os.environ.setdefault("SQLITE_CONNECT_TIMEOUT_SECONDS", "5")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-not-for-production")

# FIX [2026-07-19 P1-4]: 测试日志隔离——将 LOG_DIR 重定向到 per-session 临时目录，
# 防止 pytest 运行时通过 app.main 导入触发 logger.add() 写入生产日志路径
# `backend/logs/app.log`，污染生产日志（aa.txt P1-4）。
# 必须在 `import app.core.config` / `import app.main` 之前设置。
_TEST_LOG_DIR = os.path.join(tempfile.gettempdir(), f"pygbsentry_test_logs_{os.getpid()}")
os.makedirs(_TEST_LOG_DIR, exist_ok=True)
os.environ.setdefault("LOG_DIR", _TEST_LOG_DIR)

# Eagerly import the REAL app.core.config so that test modules which
# conditionally create a minimal `app.core.config` stub (e.g. test_bye_auth,
# test_sip_auth) find the real module already in sys.modules and MERGE their
# extra keys instead of replacing it — preventing AttributeError on
# settings.SQLALCHEMY_DATABASE_URI (and other fields) for downstream tests
# such as test_commercial_readiness_e2e that depend on the real app.
import app.core.config  # noqa: E402


# --- Database fixtures ---

@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create a test database engine using SQLite in-memory."""
    from app.db.base import Base
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test, rolled back after."""
    async_session = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback()


# --- App and client fixtures ---

@pytest_asyncio.fixture(scope="session")
async def app():
    """Create a FastAPI test application."""
    from app.main import app as _app
    yield _app


@pytest_asyncio.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- Auth fixtures ---

@pytest.fixture
def test_user_data():
    """Default test user data for registration/login."""
    return {
        "username": "testuser",
        "password": "TestPass123!",
        "email": "test@pygbsentry.local",
    }


@pytest.fixture
def admin_user_data():
    """Default admin user data."""
    return {
        "username": "admin",
        "password": "AdminPass123!",
        "email": "admin@pygbsentry.local",
    }


@pytest_asyncio.fixture
async def auth_token(client: AsyncClient, test_user_data: dict) -> str:
    """Get an authentication token for the test user. Assumes user exists."""
    response = await client.post("/api/v1/login", json={
        "username": test_user_data["username"],
        "password": test_user_data["password"],
    })
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token", "")
    return ""


@pytest_asyncio.fixture
async def auth_headers(auth_token: str) -> dict:
    """Get authorization headers with a valid token."""
    return {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
