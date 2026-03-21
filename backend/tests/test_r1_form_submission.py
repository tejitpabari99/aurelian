"""
R1 Unit Tests — Save FormSubmission on Tool Call

Tests that the PUT /chat/{chat_id} endpoint correctly creates FormSubmission
rows when the OpenAI model issues submit_interest_form tool calls.
"""

import json
import pytest
from unittest.mock import patch

from sqlalchemy import select

import models
from tests.conftest import make_openai_response, _make_tool_call


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_chat(client) -> str:
    """Create a chat via POST and return its ID."""
    resp = await client.post("/chat", json={"messages": []})
    assert resp.status_code == 200
    return resp.json()["id"]


def _tool_call_form(call_id: str, name: str, email: str, phone_number: str) -> dict:
    """Build a submit_interest_form tool call with the given args."""
    args = json.dumps({"name": name, "email": email, "phone_number": phone_number})
    return _make_tool_call(call_id, "submit_interest_form", args)


# ---------------------------------------------------------------------------
# Test 1: Happy path — form created on tool call
# ---------------------------------------------------------------------------

async def test_form_created_on_tool_call(client, db_session):
    """
    When OpenAI returns a submit_interest_form tool call with valid args,
    a FormSubmission row should be created in the DB with the correct data.
    """
    chat_id = await _create_chat(client)

    tool_call = _tool_call_form(
        "call_abc123", name="Jane", email="jane@test.com", phone_number="555-0001"
    )

    # First call returns tool call, second call returns normal assistant message
    mock_responses = [
        make_openai_response(tool_calls=[tool_call]),
        make_openai_response(content="I've submitted the form for Jane!"),
    ]

    with patch("main.openai_client.chat.completions.create", side_effect=mock_responses):
        resp = await client.put(
            f"/chat/{chat_id}",
            json={"messages": [{"role": "user", "content": "Submit form for Jane"}]},
        )

    assert resp.status_code == 200
    data = resp.json()

    # Verify response messages contain tool call and tool response with "Success"
    tool_responses = [m for m in data["messages"] if m.get("role") == "tool"]
    assert len(tool_responses) == 1
    assert "Success" in tool_responses[0]["content"]

    # Verify FormSubmission row in DB
    result = await db_session.execute(
        select(models.FormSubmission).filter(models.FormSubmission.chat_id == chat_id)
    )
    forms = result.scalars().all()
    assert len(forms) == 1
    assert forms[0].name == "Jane"
    assert forms[0].email == "jane@test.com"
    assert forms[0].phone_number == "555-0001"
    assert forms[0].chat_id == chat_id
    assert forms[0].status is None

    # Verify form also appears in the response's form_submissions
    assert len(data["form_submissions"]) == 1
    assert data["form_submissions"][0]["name"] == "Jane"


# ---------------------------------------------------------------------------
# Test 2: Partial args — missing email and phone → validation error
# ---------------------------------------------------------------------------

async def test_form_rejected_with_partial_args(client, db_session):
    """
    When tool call arguments only contain 'name' (no email, no phone),
    validation should reject the form (empty email/phone are invalid).
    The tool response should contain a validation error and no row is created.
    """
    chat_id = await _create_chat(client)

    args = json.dumps({"name": "Jane"})
    tool_call = _make_tool_call("call_partial", "submit_interest_form", args)

    mock_responses = [
        make_openai_response(tool_calls=[tool_call]),
        make_openai_response(content="There was a validation error with the form."),
    ]

    with patch("main.openai_client.chat.completions.create", side_effect=mock_responses):
        resp = await client.put(
            f"/chat/{chat_id}",
            json={"messages": [{"role": "user", "content": "Submit form"}]},
        )

    assert resp.status_code == 200
    data = resp.json()

    # Tool response should contain validation error
    tool_responses = [m for m in data["messages"] if m.get("role") == "tool"]
    assert len(tool_responses) == 1
    assert "Validation Error" in tool_responses[0]["content"]

    # No FormSubmission should be created
    result = await db_session.execute(
        select(models.FormSubmission).filter(models.FormSubmission.chat_id == chat_id)
    )
    forms = result.scalars().all()
    assert len(forms) == 0


# ---------------------------------------------------------------------------
# Test 3: Malformed JSON — no form created, no 500
# ---------------------------------------------------------------------------

async def test_form_creation_handles_malformed_json(client, db_session):
    """
    When tool call arguments are not valid JSON, no FormSubmission should
    be created. The tool response should contain 'Error'. The endpoint
    should NOT return 500.
    """
    chat_id = await _create_chat(client)

    tool_call = _make_tool_call("call_bad_json", "submit_interest_form", "not valid json")

    mock_responses = [
        make_openai_response(tool_calls=[tool_call]),
        make_openai_response(content="There was an error with the form."),
    ]

    with patch("main.openai_client.chat.completions.create", side_effect=mock_responses):
        resp = await client.put(
            f"/chat/{chat_id}",
            json={"messages": [{"role": "user", "content": "Submit form"}]},
        )

    assert resp.status_code == 200
    data = resp.json()

    # Tool response should contain error
    tool_responses = [m for m in data["messages"] if m.get("role") == "tool"]
    assert len(tool_responses) == 1
    assert "Error" in tool_responses[0]["content"]

    # No FormSubmission should be created
    result = await db_session.execute(
        select(models.FormSubmission).filter(models.FormSubmission.chat_id == chat_id)
    )
    forms = result.scalars().all()
    assert len(forms) == 0


# ---------------------------------------------------------------------------
# Test 4: Multiple tool calls — each creates its own form
# ---------------------------------------------------------------------------

async def test_multiple_tool_calls_create_multiple_forms(client, db_session):
    """
    When OpenAI returns 2 submit_interest_form tool calls in one response,
    2 separate FormSubmission rows should be created.
    """
    chat_id = await _create_chat(client)

    tool_call_1 = _tool_call_form(
        "call_001", name="Alice", email="alice@test.com", phone_number="555-1111"
    )
    tool_call_2 = _tool_call_form(
        "call_002", name="Bob", email="bob@test.com", phone_number="555-2222"
    )

    mock_responses = [
        make_openai_response(tool_calls=[tool_call_1, tool_call_2]),
        make_openai_response(content="Both forms submitted!"),
    ]

    with patch("main.openai_client.chat.completions.create", side_effect=mock_responses):
        resp = await client.put(
            f"/chat/{chat_id}",
            json={"messages": [{"role": "user", "content": "Submit two forms"}]},
        )

    assert resp.status_code == 200
    data = resp.json()

    # Verify 2 tool responses
    tool_responses = [m for m in data["messages"] if m.get("role") == "tool"]
    assert len(tool_responses) == 2
    assert all("Success" in tr["content"] for tr in tool_responses)

    # Verify 2 FormSubmission rows in DB
    result = await db_session.execute(
        select(models.FormSubmission).filter(models.FormSubmission.chat_id == chat_id)
    )
    forms = result.scalars().all()
    assert len(forms) == 2
    names = {f.name for f in forms}
    assert names == {"Alice", "Bob"}

    # Also in response
    assert len(data["form_submissions"]) == 2


# ---------------------------------------------------------------------------
# Test 5: Non-form tool call — no FormSubmission, just "Success"
# ---------------------------------------------------------------------------

async def test_non_form_tool_call_ignored(client, db_session):
    """
    When OpenAI returns a tool call for a function other than
    submit_interest_form, no FormSubmission should be created.
    The tool response content should be "Success".
    """
    chat_id = await _create_chat(client)

    tool_call = _make_tool_call(
        "call_other", "some_other_tool", json.dumps({"foo": "bar"})
    )

    mock_responses = [
        make_openai_response(tool_calls=[tool_call]),
        make_openai_response(content="Done with other tool."),
    ]

    with patch("main.openai_client.chat.completions.create", side_effect=mock_responses):
        resp = await client.put(
            f"/chat/{chat_id}",
            json={"messages": [{"role": "user", "content": "Do other thing"}]},
        )

    assert resp.status_code == 200
    data = resp.json()

    # Tool response should be plain "Success"
    tool_responses = [m for m in data["messages"] if m.get("role") == "tool"]
    assert len(tool_responses) == 1
    assert tool_responses[0]["content"] == "Success"

    # No FormSubmission should be created
    result = await db_session.execute(
        select(models.FormSubmission).filter(models.FormSubmission.chat_id == chat_id)
    )
    forms = result.scalars().all()
    assert len(forms) == 0
    assert len(data["form_submissions"]) == 0
