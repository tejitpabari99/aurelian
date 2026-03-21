"""
Shared fixtures for backend tests.

Provides:
- An in-memory async SQLite database (isolated per test)
- An httpx AsyncClient wired to the FastAPI app
- Helper to build mock OpenAI responses
"""

import pytest
import pytest_asyncio
from unittest.mock import MagicMock
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from database import Base
from main import app, get_db

# ---------------------------------------------------------------------------
# Test database (in-memory SQLite, created fresh for each test)
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite+aiosqlite://"  # in-memory


@pytest_asyncio.fixture
async def db_session():
    """Yield an async session backed by an in-memory SQLite DB."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    TestSession = async_sessionmaker(
        bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
    )
    async with TestSession() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session):
    """
    Yield an httpx AsyncClient that talks to the FastAPI app,
    with the DB dependency overridden to use the test session.
    """

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# OpenAI mock helpers
# ---------------------------------------------------------------------------

def _make_tool_call(call_id: str, name: str, arguments: str) -> dict:
    """Build a single tool_call dict matching OpenAI's schema."""
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": arguments,
        },
    }


def _make_assistant_message(content: str | None = None, tool_calls: list | None = None) -> dict:
    """Build a dict that looks like `resp.choices[0].message.model_dump()`."""
    msg = {
        "role": "assistant",
        "content": content,
        "tool_calls": tool_calls,
        "function_call": None,
    }
    return msg


def make_openai_response(content: str | None = None, tool_calls: list | None = None):
    """
    Return a MagicMock that quacks like an OpenAI ChatCompletion response.
    `resp.choices[0].message.model_dump()` returns the constructed dict.
    """
    msg_dict = _make_assistant_message(content=content, tool_calls=tool_calls)
    message_mock = MagicMock()
    message_mock.model_dump.return_value = msg_dict
    choice_mock = MagicMock()
    choice_mock.message = message_mock
    resp_mock = MagicMock()
    resp_mock.choices = [choice_mock]
    return resp_mock
