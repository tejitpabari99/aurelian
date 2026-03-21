"""
R2 Unit Tests — Update & Delete Form Submissions

Tests for:
- REST API: PUT /form/{form_id}, DELETE /form/{form_id}, GET /chat/{chat_id}/forms with status filter
- Chat Bot: update_form_submission and delete_form_submission tool call handlers
- Status validation on FormSubmissionUpdate and FormSubmissionCreate
"""

import json
import pytest
from unittest.mock import patch

from sqlalchemy import select

import crud
import models
import schemas
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


async def _create_form(db_session, chat_id: str, name: str = "John",
                       email: str = "john@test.com",
                       phone_number: str = "555-1234",
                       status: int | None = None) -> models.FormSubmission:
    """Create a FormSubmission directly in the DB and return it."""
    form_data = schemas.FormSubmissionCreate(
        name=name, email=email, phone_number=phone_number,
        chat_id=chat_id, status=status,
    )
    return await crud.form.create(db=db_session, obj_in=form_data)


# ===========================================================================
# REST API Tests
# ===========================================================================


# ---------------------------------------------------------------------------
# Test 1: Update form name
# ---------------------------------------------------------------------------

async def test_update_form_name(client, db_session):
    """PUT /form/{id} with { name: "Jane" } updates only the name."""
    chat_id = await _create_chat(client)
    form = await _create_form(db_session, chat_id, name="John")

    resp = await client.put(f"/form/{form.id}", json={"name": "Jane"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Jane"
    assert data["email"] == "john@test.com"  # unchanged
    assert data["phone_number"] == "555-1234"  # unchanged


# ---------------------------------------------------------------------------
# Test 2: Update form status (valid)
# ---------------------------------------------------------------------------

async def test_update_form_status_valid(client, db_session):
    """PUT /form/{id} with { status: 2 } sets status to IN PROGRESS."""
    chat_id = await _create_chat(client)
    form = await _create_form(db_session, chat_id)

    resp = await client.put(f"/form/{form.id}", json={"status": 2})
    assert resp.status_code == 200
    assert resp.json()["status"] == 2


# ---------------------------------------------------------------------------
# Test 3: Update form status (invalid — 5)
# ---------------------------------------------------------------------------

async def test_update_form_status_invalid(client, db_session):
    """PUT /form/{id} with { status: 5 } returns 422."""
    chat_id = await _create_chat(client)
    form = await _create_form(db_session, chat_id)

    resp = await client.put(f"/form/{form.id}", json={"status": 5})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Test 4: Update form status (invalid — 0)
# ---------------------------------------------------------------------------

async def test_update_form_status_zero_invalid(client, db_session):
    """PUT /form/{id} with { status: 0 } returns 422 (0 is not valid)."""
    chat_id = await _create_chat(client)
    form = await _create_form(db_session, chat_id)

    resp = await client.put(f"/form/{form.id}", json={"status": 0})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Test 5: Update form status to null (valid — clears status)
# ---------------------------------------------------------------------------

async def test_update_form_status_null_valid(client, db_session):
    """PUT /form/{id} with { status: null } clears the status."""
    chat_id = await _create_chat(client)
    form = await _create_form(db_session, chat_id, status=1)

    resp = await client.put(f"/form/{form.id}", json={"status": None})
    assert resp.status_code == 200
    assert resp.json()["status"] is None


# ---------------------------------------------------------------------------
# Test 6: Update form — not found
# ---------------------------------------------------------------------------

async def test_update_form_not_found(client):
    """PUT /form/nonexistent returns 404."""
    resp = await client.put("/form/nonexistent", json={"name": "Jane"})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Form submission not found"


# ---------------------------------------------------------------------------
# Test 7: Update form — empty body (no-op)
# ---------------------------------------------------------------------------

async def test_update_form_empty_body(client, db_session):
    """PUT /form/{id} with {} returns the form unchanged."""
    chat_id = await _create_chat(client)
    form = await _create_form(db_session, chat_id, name="John", email="john@test.com")

    resp = await client.put(f"/form/{form.id}", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "John"
    assert data["email"] == "john@test.com"


# ---------------------------------------------------------------------------
# Test 8: Delete form — happy path
# ---------------------------------------------------------------------------

async def test_delete_form(client, db_session):
    """DELETE /form/{id} deletes the form and returns it."""
    chat_id = await _create_chat(client)
    form = await _create_form(db_session, chat_id, name="John")

    resp = await client.delete(f"/form/{form.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == form.id
    assert data["name"] == "John"

    # Confirm it's actually gone
    result = await db_session.execute(
        select(models.FormSubmission).filter(models.FormSubmission.id == form.id)
    )
    assert result.scalars().first() is None


# ---------------------------------------------------------------------------
# Test 9: Delete form — not found
# ---------------------------------------------------------------------------

async def test_delete_form_not_found(client):
    """DELETE /form/nonexistent returns 404."""
    resp = await client.delete("/form/nonexistent")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Form submission not found"


# ---------------------------------------------------------------------------
# Test 10: Delete form — idempotency (double delete)
# ---------------------------------------------------------------------------

async def test_delete_form_idempotency(client, db_session):
    """Deleting the same form twice: first returns 200, second returns 404."""
    chat_id = await _create_chat(client)
    form = await _create_form(db_session, chat_id)

    resp1 = await client.delete(f"/form/{form.id}")
    assert resp1.status_code == 200

    resp2 = await client.delete(f"/form/{form.id}")
    assert resp2.status_code == 404


# ---------------------------------------------------------------------------
# Test 11: GET forms filtered by status
# ---------------------------------------------------------------------------

async def test_get_chat_forms_filter_by_status(client, db_session):
    """GET /chat/{id}/forms?status=2 returns only IN PROGRESS forms."""
    chat_id = await _create_chat(client)
    await _create_form(db_session, chat_id, name="A", status=1)
    await _create_form(db_session, chat_id, name="B", status=2)
    await _create_form(db_session, chat_id, name="C", status=3)

    resp = await client.get(f"/chat/{chat_id}/forms?status=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "B"
    assert data[0]["status"] == 2


# ---------------------------------------------------------------------------
# Test 12: GET forms filtered — no match
# ---------------------------------------------------------------------------

async def test_get_chat_forms_filter_no_match(client, db_session):
    """GET /chat/{id}/forms?status=3 with no COMPLETED forms returns []."""
    chat_id = await _create_chat(client)
    await _create_form(db_session, chat_id, name="A", status=1)

    resp = await client.get(f"/chat/{chat_id}/forms?status=3")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Test 13: GET forms — no filter returns all
# ---------------------------------------------------------------------------

async def test_get_chat_forms_no_filter(client, db_session):
    """GET /chat/{id}/forms without status param returns all forms."""
    chat_id = await _create_chat(client)
    await _create_form(db_session, chat_id, name="A", status=1)
    await _create_form(db_session, chat_id, name="B", status=2)
    await _create_form(db_session, chat_id, name="C", status=3)

    resp = await client.get(f"/chat/{chat_id}/forms")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


# ---------------------------------------------------------------------------
# Test: Update multiple fields at once
# ---------------------------------------------------------------------------

async def test_update_form_multiple_fields(client, db_session):
    """PUT /form/{id} can update name, email, and status together."""
    chat_id = await _create_chat(client)
    form = await _create_form(db_session, chat_id, name="John", email="john@test.com")

    resp = await client.put(f"/form/{form.id}", json={
        "name": "Jane Smith",
        "email": "jane@new.com",
        "status": 3,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Jane Smith"
    assert data["email"] == "jane@new.com"
    assert data["status"] == 3
    assert data["phone_number"] == "555-1234"  # unchanged


# ---------------------------------------------------------------------------
# Test: Status validation on FormSubmissionCreate
# ---------------------------------------------------------------------------

async def test_create_form_status_invalid():
    """FormSubmissionCreate rejects invalid status values."""
    with pytest.raises(Exception):  # Pydantic ValidationError
        schemas.FormSubmissionCreate(
            name="Test", email="t@t.com", phone_number="555",
            chat_id="abc", status=5,
        )


async def test_create_form_status_valid():
    """FormSubmissionCreate accepts valid status values."""
    form = schemas.FormSubmissionCreate(
        name="Test", email="t@t.com", phone_number="555",
        chat_id="abc", status=2,
    )
    assert form.status == 2


# ===========================================================================
# Chat Bot Tool Tests
# ===========================================================================


# ---------------------------------------------------------------------------
# Test 14: Update form via chat — happy path
# ---------------------------------------------------------------------------

async def test_update_form_via_chat(client, db_session):
    """
    When OpenAI returns update_form_submission with valid form_id and name,
    the form should be updated in the DB.
    """
    chat_id = await _create_chat(client)
    form = await _create_form(db_session, chat_id, name="John")

    tool_call = _make_tool_call(
        "call_update_1",
        "update_form_submission",
        json.dumps({"form_id": form.id, "name": "Updated Name"}),
    )

    mock_responses = [
        make_openai_response(tool_calls=[tool_call]),
        make_openai_response(content="I've updated the form!"),
    ]

    with patch("main.openai_client.chat.completions.create", side_effect=mock_responses):
        resp = await client.put(
            f"/chat/{chat_id}",
            json={"messages": [{"role": "user", "content": "Update the form name"}]},
        )

    assert resp.status_code == 200
    data = resp.json()

    # Tool response should contain "Success"
    tool_responses = [m for m in data["messages"] if m.get("role") == "tool"]
    assert len(tool_responses) == 1
    assert "Success" in tool_responses[0]["content"]

    # Verify DB was updated
    await db_session.refresh(form)
    assert form.name == "Updated Name"
    assert form.email == "john@test.com"  # unchanged


# ---------------------------------------------------------------------------
# Test 15: Update form via chat — nonexistent form_id
# ---------------------------------------------------------------------------

async def test_update_form_via_chat_invalid_id(client, db_session):
    """
    When OpenAI returns update_form_submission with a nonexistent form_id,
    the tool response should contain an error.
    """
    chat_id = await _create_chat(client)

    tool_call = _make_tool_call(
        "call_update_bad",
        "update_form_submission",
        json.dumps({"form_id": "nonexistent_id", "name": "New Name"}),
    )

    mock_responses = [
        make_openai_response(tool_calls=[tool_call]),
        make_openai_response(content="I couldn't find that form."),
    ]

    with patch("main.openai_client.chat.completions.create", side_effect=mock_responses):
        resp = await client.put(
            f"/chat/{chat_id}",
            json={"messages": [{"role": "user", "content": "Update form nonexistent"}]},
        )

    assert resp.status_code == 200
    data = resp.json()

    tool_responses = [m for m in data["messages"] if m.get("role") == "tool"]
    assert len(tool_responses) == 1
    assert "Error" in tool_responses[0]["content"]
    assert "not found" in tool_responses[0]["content"]


# ---------------------------------------------------------------------------
# Test 16: Delete form via chat — happy path
# ---------------------------------------------------------------------------

async def test_delete_form_via_chat(client, db_session):
    """
    When OpenAI returns delete_form_submission with a valid form_id,
    the form should be deleted from the DB.
    """
    chat_id = await _create_chat(client)
    form = await _create_form(db_session, chat_id, name="John")

    tool_call = _make_tool_call(
        "call_delete_1",
        "delete_form_submission",
        json.dumps({"form_id": form.id}),
    )

    mock_responses = [
        make_openai_response(tool_calls=[tool_call]),
        make_openai_response(content="The form has been deleted."),
    ]

    with patch("main.openai_client.chat.completions.create", side_effect=mock_responses):
        resp = await client.put(
            f"/chat/{chat_id}",
            json={"messages": [{"role": "user", "content": "Delete the form"}]},
        )

    assert resp.status_code == 200
    data = resp.json()

    # Tool response should contain "Success"
    tool_responses = [m for m in data["messages"] if m.get("role") == "tool"]
    assert len(tool_responses) == 1
    assert "Success" in tool_responses[0]["content"]

    # Verify form is gone from DB
    result = await db_session.execute(
        select(models.FormSubmission).filter(models.FormSubmission.id == form.id)
    )
    assert result.scalars().first() is None


# ---------------------------------------------------------------------------
# Test 17: Delete form via chat — nonexistent form_id
# ---------------------------------------------------------------------------

async def test_delete_form_via_chat_invalid_id(client, db_session):
    """
    When OpenAI returns delete_form_submission with a nonexistent form_id,
    the tool response should contain an error.
    """
    chat_id = await _create_chat(client)

    tool_call = _make_tool_call(
        "call_delete_bad",
        "delete_form_submission",
        json.dumps({"form_id": "nonexistent_id"}),
    )

    mock_responses = [
        make_openai_response(tool_calls=[tool_call]),
        make_openai_response(content="I couldn't find that form."),
    ]

    with patch("main.openai_client.chat.completions.create", side_effect=mock_responses):
        resp = await client.put(
            f"/chat/{chat_id}",
            json={"messages": [{"role": "user", "content": "Delete form nonexistent"}]},
        )

    assert resp.status_code == 200
    data = resp.json()

    tool_responses = [m for m in data["messages"] if m.get("role") == "tool"]
    assert len(tool_responses) == 1
    assert "Error" in tool_responses[0]["content"]
    assert "not found" in tool_responses[0]["content"]


# ---------------------------------------------------------------------------
# Test 18: Update form via chat — invalid status
# ---------------------------------------------------------------------------

async def test_update_form_via_chat_invalid_status(client, db_session):
    """
    When OpenAI returns update_form_submission with status=99,
    the tool response should contain a validation error.
    Form status should remain unchanged.
    """
    chat_id = await _create_chat(client)
    form = await _create_form(db_session, chat_id, name="John", status=1)

    tool_call = _make_tool_call(
        "call_update_bad_status",
        "update_form_submission",
        json.dumps({"form_id": form.id, "status": 99}),
    )

    mock_responses = [
        make_openai_response(tool_calls=[tool_call]),
        make_openai_response(content="There was a validation error."),
    ]

    with patch("main.openai_client.chat.completions.create", side_effect=mock_responses):
        resp = await client.put(
            f"/chat/{chat_id}",
            json={"messages": [{"role": "user", "content": "Set status to 99"}]},
        )

    assert resp.status_code == 200
    data = resp.json()

    tool_responses = [m for m in data["messages"] if m.get("role") == "tool"]
    assert len(tool_responses) == 1
    assert "Error" in tool_responses[0]["content"]

    # Verify status unchanged in DB
    await db_session.refresh(form)
    assert form.status == 1


# ---------------------------------------------------------------------------
# Test: Update form via chat — missing form_id
# ---------------------------------------------------------------------------

async def test_update_form_via_chat_missing_form_id(client, db_session):
    """
    When OpenAI returns update_form_submission without form_id,
    the tool response should contain 'form_id is required'.
    """
    chat_id = await _create_chat(client)

    tool_call = _make_tool_call(
        "call_update_no_id",
        "update_form_submission",
        json.dumps({"name": "New Name"}),  # no form_id
    )

    mock_responses = [
        make_openai_response(tool_calls=[tool_call]),
        make_openai_response(content="I need the form ID."),
    ]

    with patch("main.openai_client.chat.completions.create", side_effect=mock_responses):
        resp = await client.put(
            f"/chat/{chat_id}",
            json={"messages": [{"role": "user", "content": "Update some form"}]},
        )

    assert resp.status_code == 200
    data = resp.json()

    tool_responses = [m for m in data["messages"] if m.get("role") == "tool"]
    assert len(tool_responses) == 1
    assert "form_id is required" in tool_responses[0]["content"]


# ---------------------------------------------------------------------------
# Test: Delete form via chat — missing form_id
# ---------------------------------------------------------------------------

async def test_delete_form_via_chat_missing_form_id(client, db_session):
    """
    When OpenAI returns delete_form_submission without form_id,
    the tool response should contain 'form_id is required'.
    """
    chat_id = await _create_chat(client)

    tool_call = _make_tool_call(
        "call_delete_no_id",
        "delete_form_submission",
        json.dumps({}),  # no form_id
    )

    mock_responses = [
        make_openai_response(tool_calls=[tool_call]),
        make_openai_response(content="I need the form ID."),
    ]

    with patch("main.openai_client.chat.completions.create", side_effect=mock_responses):
        resp = await client.put(
            f"/chat/{chat_id}",
            json={"messages": [{"role": "user", "content": "Delete some form"}]},
        )

    assert resp.status_code == 200
    data = resp.json()

    tool_responses = [m for m in data["messages"] if m.get("role") == "tool"]
    assert len(tool_responses) == 1
    assert "form_id is required" in tool_responses[0]["content"]


# ---------------------------------------------------------------------------
# Test: Update form via chat — malformed JSON
# ---------------------------------------------------------------------------

async def test_update_form_via_chat_malformed_json(client, db_session):
    """
    When OpenAI returns update_form_submission with malformed JSON args,
    the tool response should contain an error. No crash.
    """
    chat_id = await _create_chat(client)

    tool_call = _make_tool_call(
        "call_update_bad_json",
        "update_form_submission",
        "not valid json{{{",
    )

    mock_responses = [
        make_openai_response(tool_calls=[tool_call]),
        make_openai_response(content="There was a parsing error."),
    ]

    with patch("main.openai_client.chat.completions.create", side_effect=mock_responses):
        resp = await client.put(
            f"/chat/{chat_id}",
            json={"messages": [{"role": "user", "content": "Update form"}]},
        )

    assert resp.status_code == 200
    data = resp.json()

    tool_responses = [m for m in data["messages"] if m.get("role") == "tool"]
    assert len(tool_responses) == 1
    assert "Error" in tool_responses[0]["content"]


# ---------------------------------------------------------------------------
# Test: Delete form via chat — malformed JSON
# ---------------------------------------------------------------------------

async def test_delete_form_via_chat_malformed_json(client, db_session):
    """
    When OpenAI returns delete_form_submission with malformed JSON args,
    the tool response should contain an error. No crash.
    """
    chat_id = await _create_chat(client)

    tool_call = _make_tool_call(
        "call_delete_bad_json",
        "delete_form_submission",
        "not valid json{{{",
    )

    mock_responses = [
        make_openai_response(tool_calls=[tool_call]),
        make_openai_response(content="There was a parsing error."),
    ]

    with patch("main.openai_client.chat.completions.create", side_effect=mock_responses):
        resp = await client.put(
            f"/chat/{chat_id}",
            json={"messages": [{"role": "user", "content": "Delete form"}]},
        )

    assert resp.status_code == 200
    data = resp.json()

    tool_responses = [m for m in data["messages"] if m.get("role") == "tool"]
    assert len(tool_responses) == 1
    assert "Error" in tool_responses[0]["content"]


# ---------------------------------------------------------------------------
# Test: Update form via chat only updates provided fields (partial update)
# ---------------------------------------------------------------------------

async def test_update_form_via_chat_partial_update(client, db_session):
    """
    When the LLM only sends form_id + name, email and phone should be unchanged.
    """
    chat_id = await _create_chat(client)
    form = await _create_form(
        db_session, chat_id, name="John", email="john@test.com",
        phone_number="555-1234", status=1,
    )

    tool_call = _make_tool_call(
        "call_partial_update",
        "update_form_submission",
        json.dumps({"form_id": form.id, "name": "Jane"}),  # only name
    )

    mock_responses = [
        make_openai_response(tool_calls=[tool_call]),
        make_openai_response(content="Updated the name."),
    ]

    with patch("main.openai_client.chat.completions.create", side_effect=mock_responses):
        resp = await client.put(
            f"/chat/{chat_id}",
            json={"messages": [{"role": "user", "content": "Change name to Jane"}]},
        )

    assert resp.status_code == 200

    # Verify only name changed
    await db_session.refresh(form)
    assert form.name == "Jane"
    assert form.email == "john@test.com"
    assert form.phone_number == "555-1234"
    assert form.status == 1
