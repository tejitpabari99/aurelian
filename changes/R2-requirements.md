# R2 — Add Update & Delete Functionality for Form Submissions (Task 2)

## Requirement Summary

From the README (Task 2):
> We want to allow users to additionally **update** their form submissions and **delete** their form submissions via the **chat interface**. Augment the chat endpoint with additional logic to support this.
>
> We will eventually want to be able to update the form submissions via the UI as well. Flesh out the **REST API** for working with FormSubmissions. Include at least the following endpoints and requirements:
> 1. **Update a form submission.** Should be able to update name, email, phone number, and status. Add a way to validate the status field. It should be either None, 1, 2, or 3. 1 = "TO DO", 2 = "IN PROGRESS", 3 = "COMPLETED"
> 2. **Get all form submissions for a specific chat.** Should be able to filter by status
> 3. **Delete a form submission.**

Task 2 has **two deliverables**:

### Deliverable A: Chat Bot Augmentation (Update & Delete via Chat)
Add new OpenAI tool definitions (`update_form_submission`, `delete_form_submission`) to the `PUT /chat/{chat_id}` endpoint so users can update or delete form submissions through the conversational interface.

### Deliverable B: REST API for Form Submissions
Expose dedicated REST endpoints for updating, filtering, and deleting form submissions — independent of the chat interface — for future UI integration.

---

## Current State (Post-R1 / Post-existing R2 work)

### What already exists
| Component | Current State |
|---|---|
| `FormSubmission` DB model | Complete — id, created_at, chat_id (FK), name, phone_number, email, status (Integer) |
| `schemas.FormSubmission` | Response schema with id, created_at, name, phone_number, email, status |
| `schemas.FormSubmissionCreate` | name, phone_number, email, chat_id, status |
| `schemas.FormSubmissionUpdate` | Optional name, phone_number, email, status — **already defined but unused** |
| `crud.form` | `.create()`, `.get()`, `.get_multi()`, `.update()`, `.remove()` — all available |
| `PUT /chat/{chat_id}` | Handles `submit_interest_form` tool call only |
| `GET /chat/{chat_id}/forms` | Returns all forms for a chat — **no status filtering** |
| `GET /chat/{chat_id}` | Returns chat with eager-loaded form_submissions |
| OpenAI tools array | Only contains `submit_interest_form` definition |

### What's missing for Task 2
| Component | Gap |
|---|---|
| OpenAI tool: `update_form_submission` | Not defined. No tool definition, no handler in PUT endpoint. |
| OpenAI tool: `delete_form_submission` | Not defined. No tool definition, no handler in PUT endpoint. |
| `PUT /form/{form_id}` REST endpoint | Does not exist. |
| `DELETE /form/{form_id}` REST endpoint | Does not exist. |
| Status validation | No validation that status must be None, 1, 2, or 3. |
| Status filtering on `GET /chat/{chat_id}/forms` | No `status` query parameter. |
| `SYSTEM_TEMPLATE` | Empty string — no instructions for the LLM about available tools. |

---

## Changes Required

### 1. Status Validation — `schemas.py`

**What:** Add validation to `FormSubmissionUpdate` (and optionally `FormSubmissionCreate`) so the `status` field only accepts `None`, `1`, `2`, or `3`.

**File:** `backend/schemas.py`

**Add a Pydantic validator to `FormSubmissionUpdate`:**

```python
from pydantic import BaseModel, field_validator

class FormSubmissionUpdate(BaseModel):
    name: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    status: Optional[int] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v is not None and v not in (1, 2, 3):
            raise ValueError("status must be None, 1 (TO DO), 2 (IN PROGRESS), or 3 (COMPLETED)")
        return v
```

**Also add to `FormSubmissionCreate`** for consistency:
```python
class FormSubmissionCreate(BaseModel):
    name: str
    phone_number: str
    email: str
    chat_id: str
    status: Optional[int] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v is not None and v not in (1, 2, 3):
            raise ValueError("status must be None, 1 (TO DO), 2 (IN PROGRESS), or 3 (COMPLETED)")
        return v
```

**Status mapping (for reference, not stored in DB):**
| Value | Label |
|---|---|
| `None` | No status / unset |
| `1` | TO DO |
| `2` | IN PROGRESS |
| `3` | COMPLETED |

**Why Pydantic validator instead of DB constraint:** Pydantic validation gives clear 422 error messages via FastAPI. DB constraints give opaque 500s. Both can be used, but Pydantic is the primary validation layer.

---

### 2. REST API — `PUT /form/{form_id}` (Update Form Submission)

**What:** Endpoint to update a form submission's name, email, phone_number, and/or status.

**File:** `backend/main.py`

```python
@app.put("/form/{form_id}", response_model=schemas.FormSubmission)
async def update_form(
    form_id: str,
    data: schemas.FormSubmissionUpdate,
    db: AsyncSession = Depends(get_db),
):
    logger.info("PUT /form/%s — updating form", form_id)
    form = await crud.form.get(db, id=form_id)
    if form is None:
        logger.warning("Form not found: form_id=%s", form_id)
        raise HTTPException(status_code=404, detail="Form submission not found")

    updated_form = await crud.form.update(db, db_obj=form, obj_in=data)
    logger.info("PUT /form/%s — updated successfully", form_id)
    return updated_form
```

**Behavior:**
- Accepts partial updates (all fields optional via `FormSubmissionUpdate`).
- Returns 404 if form doesn't exist.
- Returns 422 if status value is invalid (via Pydantic validator).
- Uses existing `crud.form.update()` — only updates fields present in the request body (`exclude_unset=True` in the CRUD layer).

**Request body examples:**
```json
// Update name only
{ "name": "Jane Smith" }

// Update status only
{ "status": 2 }

// Update multiple fields
{ "name": "Jane Smith", "email": "jane@new.com", "status": 3 }

// Clear status
{ "status": null }
```

**Error responses:**
```json
// 404 — form not found
{ "detail": "Form submission not found" }

// 422 — invalid status
{ "detail": [{ "msg": "Value error, status must be None, 1 (TO DO), 2 (IN PROGRESS), or 3 (COMPLETED)", ... }] }
```

---

### 3. REST API — `DELETE /form/{form_id}` (Delete Form Submission)

**What:** Endpoint to delete a form submission by ID.

**File:** `backend/main.py`

```python
@app.delete("/form/{form_id}", response_model=schemas.FormSubmission)
async def delete_form(
    form_id: str,
    db: AsyncSession = Depends(get_db),
):
    logger.info("DELETE /form/%s — deleting form", form_id)
    form = await crud.form.get(db, id=form_id)
    if form is None:
        logger.warning("Form not found: form_id=%s", form_id)
        raise HTTPException(status_code=404, detail="Form submission not found")

    deleted_form = await crud.form.remove(db, id=form_id)
    logger.info("DELETE /form/%s — deleted successfully", form_id)
    return deleted_form
```

**Behavior:**
- Returns the deleted form submission in the response body (for confirmation/undo).
- Returns 404 if form doesn't exist.
- Uses existing `crud.form.remove()`.

---

### 4. REST API — Add Status Filtering to `GET /chat/{chat_id}/forms`

**What:** Add an optional `status` query parameter to filter form submissions by status.

**File:** `backend/main.py`

**Before:**
```python
@app.get("/chat/{chat_id}/forms", response_model=list[schemas.FormSubmission])
async def get_chat_forms(chat_id: str, db: AsyncSession = Depends(get_db)):
    forms = await crud.form.get_multi(
        db, filters=[models.FormSubmission.chat_id == chat_id]
    )
    return forms
```

**After:**
```python
@app.get("/chat/{chat_id}/forms", response_model=list[schemas.FormSubmission])
async def get_chat_forms(
    chat_id: str,
    status: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    logger.info("GET /chat/%s/forms — status filter=%s", chat_id, status)
    filters = [models.FormSubmission.chat_id == chat_id]
    if status is not None:
        filters.append(models.FormSubmission.status == status)
    forms = await crud.form.get_multi(db, filters=filters)
    logger.info("GET /chat/%s/forms — returning %d forms", chat_id, len(forms))
    return forms
```

**Import needed:** `from typing import Optional` (may already be imported).

**Usage examples:**
- `GET /chat/{chat_id}/forms` — all forms for this chat
- `GET /chat/{chat_id}/forms?status=1` — only TO DO forms
- `GET /chat/{chat_id}/forms?status=2` — only IN PROGRESS forms
- `GET /chat/{chat_id}/forms?status=3` — only COMPLETED forms

**Edge case — filter for `status=null`:** This is trickier because `None` in the query param means "no filter." If we need to filter for forms with no status set, we could use a sentinel value (e.g., `status=0` or a separate `has_status=false` param). For now, this is out of scope — only filtering by numeric status values 1, 2, 3 is supported.

---

### 5. Chat Bot Augmentation — New Tool Definitions

**What:** Add `update_form_submission` and `delete_form_submission` to the OpenAI tools array so the LLM can invoke them during conversation.

**File:** `backend/main.py`

**Define the tools array as a module-level constant** (to avoid duplication between the two OpenAI calls):

```python
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "submit_interest_form",
            "description": "Submit an interest form for the user with the given properties",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "the user's name",
                    },
                    "email": {
                        "type": "string",
                        "description": "the user's email address",
                    },
                    "phone_number": {
                        "type": "string",
                        "description": "the user's phone number",
                    },
                },
                "required": ["name", "email", "phone_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_form_submission",
            "description": "Update an existing form submission. Can update the name, email, phone number, and/or status. Status must be 1 (TO DO), 2 (IN PROGRESS), or 3 (COMPLETED), or null to clear it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "form_id": {
                        "type": "string",
                        "description": "the ID of the form submission to update",
                    },
                    "name": {
                        "type": "string",
                        "description": "the updated name (optional)",
                    },
                    "email": {
                        "type": "string",
                        "description": "the updated email address (optional)",
                    },
                    "phone_number": {
                        "type": "string",
                        "description": "the updated phone number (optional)",
                    },
                    "status": {
                        "type": ["integer", "null"],
                        "description": "the updated status: 1 = TO DO, 2 = IN PROGRESS, 3 = COMPLETED, or null to clear",
                    },
                },
                "required": ["form_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_form_submission",
            "description": "Delete an existing form submission by its ID",
            "parameters": {
                "type": "object",
                "properties": {
                    "form_id": {
                        "type": "string",
                        "description": "the ID of the form submission to delete",
                    },
                },
                "required": ["form_id"],
            },
        },
    },
]
```

**Why extract to `TOOLS` constant:**
- Currently the tools array is duplicated in two places (first and second OpenAI call).
- Extracting avoids duplication and makes it easy to add tools.
- Both OpenAI calls reference `TOOLS`.

---

### 6. Chat Bot Augmentation — Tool Call Handlers in `PUT /chat/{chat_id}`

**What:** Add handling for `update_form_submission` and `delete_form_submission` tool calls alongside the existing `submit_interest_form` handler.

**File:** `backend/main.py`

**Inside the `for t in resp_message["tool_calls"]:` loop, add two new branches:**

```python
for t in resp_message["tool_calls"]:
    tool_name = t["function"]["name"]
    tool_content = "Success"

    if tool_name == "submit_interest_form":
        # ... existing handler (unchanged) ...

    elif tool_name == "update_form_submission":
        try:
            args = json.loads(t["function"]["arguments"])
            form_id = args.get("form_id")
            if not form_id:
                tool_content = "Error: form_id is required"
            else:
                form = await crud.form.get(db, id=form_id)
                if form is None:
                    tool_content = f"Error: Form submission with ID {form_id} not found"
                else:
                    update_data = schemas.FormSubmissionUpdate(
                        name=args.get("name"),
                        email=args.get("email"),
                        phone_number=args.get("phone_number"),
                        status=args.get("status"),
                    )
                    updated_form = await crud.form.update(db, db_obj=form, obj_in=update_data)
                    logger.info(
                        "FormSubmission updated via chat: id=%s, chat_id=%s",
                        updated_form.id, chat_id,
                    )
                    tool_content = f"Success. Form submission {form_id} has been updated."
        except json.JSONDecodeError as e:
            logger.error("Failed to parse update tool call arguments: %s", e)
            tool_content = "Error: Could not parse update data"
        except ValueError as e:
            logger.error("Validation error on form update: %s", e)
            tool_content = f"Error: {e}"
        except Exception as e:
            logger.error("Failed to update FormSubmission: %s", e, exc_info=True)
            tool_content = f"Error: Failed to update form — {e}"

    elif tool_name == "delete_form_submission":
        try:
            args = json.loads(t["function"]["arguments"])
            form_id = args.get("form_id")
            if not form_id:
                tool_content = "Error: form_id is required"
            else:
                form = await crud.form.get(db, id=form_id)
                if form is None:
                    tool_content = f"Error: Form submission with ID {form_id} not found"
                else:
                    await crud.form.remove(db, id=form_id)
                    logger.info(
                        "FormSubmission deleted via chat: id=%s, chat_id=%s",
                        form_id, chat_id,
                    )
                    tool_content = f"Success. Form submission {form_id} has been deleted."
        except json.JSONDecodeError as e:
            logger.error("Failed to parse delete tool call arguments: %s", e)
            tool_content = "Error: Could not parse delete data"
        except Exception as e:
            logger.error("Failed to delete FormSubmission: %s", e, exc_info=True)
            tool_content = f"Error: Failed to delete form — {e}"

    else:
        logger.debug("PUT /chat/%s — skipping unknown tool call: %s", chat_id, tool_name)

    data.messages.append(
        {
            "tool_call_id": t["id"],
            "role": "tool",
            "name": tool_name,
            "content": tool_content,
        }
    )
```

---

### 7. Update `SYSTEM_TEMPLATE` for Better Tool Usage

**What:** Provide the LLM with context about what tools are available and how to use them, particularly for update and delete operations which require a `form_id`.

**File:** `backend/main.py`

```python
SYSTEM_TEMPLATE = """You are a helpful assistant that can manage interest form submissions.

You have the following tools available:
- submit_interest_form: Collect and submit a new interest form with name, email, and phone number.
- update_form_submission: Update an existing form submission by its ID. You can update name, email, phone_number, and status (1=TO DO, 2=IN PROGRESS, 3=COMPLETED, or null to clear).
- delete_form_submission: Delete an existing form submission by its ID.

When a user wants to update or delete a form, you will need the form's ID. If the user does not provide it, ask them for it. The form ID was provided when the form was originally submitted.
"""
```

**Why:** Without system instructions, the LLM may not know when or how to use the update/delete tools. The prompt tells it about available tools and the need for `form_id`.

---

### 8. Replace Duplicated Tools Array with `TOOLS` Constant

**What:** Both OpenAI `chat.completions.create` calls in `PUT /chat/{chat_id}` currently have the tools array inline and duplicated. Replace both with the `TOOLS` constant.

**File:** `backend/main.py`

**Before (two places):**
```python
resp = openai_client.chat.completions.create(
    messages=...,
    model="gpt-4o-mini",
    tools=[{ ... submit_interest_form only ... }],
)
```

**After (both calls):**
```python
resp = openai_client.chat.completions.create(
    messages=...,
    model="gpt-4o-mini",
    tools=TOOLS,
)
```

---

## API Contract

### New: `PUT /form/{form_id}`

**Request:**
```json
{
  "name": "Jane Smith",
  "email": "jane@new.com",
  "phone_number": "555-9999",
  "status": 2
}
```
All fields optional. Only provided fields are updated.

**Response (200):**
```json
{
  "id": "form_xyz",
  "created_at": "2024-05-14T19:15:00",
  "name": "Jane Smith",
  "phone_number": "555-9999",
  "email": "jane@new.com",
  "status": 2
}
```

**Error (404):**
```json
{ "detail": "Form submission not found" }
```

**Error (422 — invalid status):**
```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "status"],
      "msg": "Value error, status must be None, 1 (TO DO), 2 (IN PROGRESS), or 3 (COMPLETED)"
    }
  ]
}
```

### New: `DELETE /form/{form_id}`

**Response (200):**
```json
{
  "id": "form_xyz",
  "created_at": "2024-05-14T19:15:00",
  "name": "Jane Smith",
  "phone_number": "555-9999",
  "email": "jane@new.com",
  "status": 2
}
```

**Error (404):**
```json
{ "detail": "Form submission not found" }
```

### Updated: `GET /chat/{chat_id}/forms?status={status}`

**Query parameters:**
| Parameter | Type | Required | Description |
|---|---|---|---|
| `status` | `int` | No | Filter by status value (1, 2, or 3). Omit for all forms. |

**Examples:**
- `GET /chat/abc123/forms` → all forms
- `GET /chat/abc123/forms?status=1` → only TO DO
- `GET /chat/abc123/forms?status=2` → only IN PROGRESS
- `GET /chat/abc123/forms?status=3` → only COMPLETED

---

## Edge Cases

### REST API Edge Cases

| # | Case | Expected Behavior |
|---|---|---|
| 1 | `PUT /form/{form_id}` with empty body `{}` | No fields updated. Returns existing form unchanged. |
| 2 | `PUT /form/{form_id}` with `status: 5` | Returns 422 — validation error. |
| 3 | `PUT /form/{form_id}` with `status: 0` | Returns 422 — validation error (0 is not valid). |
| 4 | `PUT /form/{form_id}` with `status: null` | Clears status to None. Valid. |
| 5 | `PUT /form/nonexistent` | Returns 404. |
| 6 | `DELETE /form/nonexistent` | Returns 404. |
| 7 | `DELETE /form/{form_id}` then `DELETE /form/{form_id}` again | First returns 200, second returns 404. |
| 8 | `GET /chat/{chat_id}/forms?status=1` with no matching forms | Returns `[]`. |
| 9 | `GET /chat/{chat_id}/forms?status=99` | Returns `[]` (no forms match, no validation on filter param). |

### Chat Bot Edge Cases

| # | Case | Expected Behavior |
|---|---|---|
| 10 | User asks to update but doesn't provide form_id | LLM should ask for the form_id before calling the tool. System prompt guides this. |
| 11 | LLM calls `update_form_submission` with nonexistent form_id | Tool returns `"Error: Form submission with ID {id} not found"`. LLM relays error to user. |
| 12 | LLM calls `update_form_submission` with invalid status | `ValueError` caught from Pydantic validator. Tool returns error message. LLM relays. |
| 13 | LLM calls `delete_form_submission` with nonexistent form_id | Tool returns `"Error: Form submission with ID {id} not found"`. LLM relays. |
| 14 | LLM calls `update_form_submission` without form_id arg | Tool returns `"Error: form_id is required"`. |
| 15 | LLM calls `delete_form_submission` without form_id arg | Tool returns `"Error: form_id is required"`. |
| 16 | LLM calls `update_form_submission` with malformed JSON arguments | Caught by `json.JSONDecodeError`. Tool returns error. |
| 17 | User asks to update a form from a different chat | The tool doesn't restrict by chat_id — it updates any form by ID. This is acceptable since the user knows the ID. |
| 18 | User submits a form, then immediately asks to update it | Works — the form_id was returned in the submission success message. |
| 19 | Multiple tool calls in one response (e.g., update + delete) | Each handled independently in the loop. |

---

## Logging Specification

| Level | When | Message Format |
|---|---|---|
| `INFO` | Form updated via REST | `"PUT /form/%s — updated successfully"` |
| `INFO` | Form deleted via REST | `"DELETE /form/%s — deleted successfully"` |
| `INFO` | Form updated via chat | `"FormSubmission updated via chat: id=%s, chat_id=%s"` |
| `INFO` | Form deleted via chat | `"FormSubmission deleted via chat: id=%s, chat_id=%s"` |
| `WARNING` | Form not found (REST) | `"Form not found: form_id=%s"` |
| `ERROR` | Parse failure (chat tools) | `"Failed to parse update/delete tool call arguments: %s"` |
| `ERROR` | Validation error (chat tools) | `"Validation error on form update: %s"` |
| `ERROR` | Any other exception (chat tools) | `"Failed to update/delete FormSubmission: %s"` (with `exc_info=True`) |

---

## Testing Plan

### Unit Tests (file: `backend/tests/test_r2_form_crud.py`)

#### REST API Tests

##### Test 1: `test_update_form_name`
- **Setup:** Create a chat + FormSubmission (name="John").
- **Act:** `PUT /form/{form_id}` with `{ "name": "Jane" }`
- **Assert:** Response 200, returned form has name="Jane". Other fields unchanged.

##### Test 2: `test_update_form_status_valid`
- **Setup:** Create a chat + FormSubmission.
- **Act:** `PUT /form/{form_id}` with `{ "status": 2 }`
- **Assert:** Response 200, status=2.

##### Test 3: `test_update_form_status_invalid`
- **Setup:** Create a chat + FormSubmission.
- **Act:** `PUT /form/{form_id}` with `{ "status": 5 }`
- **Assert:** Response 422, error message mentions valid values.

##### Test 4: `test_update_form_status_zero_invalid`
- **Setup:** Create a chat + FormSubmission.
- **Act:** `PUT /form/{form_id}` with `{ "status": 0 }`
- **Assert:** Response 422.

##### Test 5: `test_update_form_status_null_valid`
- **Setup:** Create a chat + FormSubmission with status=1.
- **Act:** `PUT /form/{form_id}` with `{ "status": null }`
- **Assert:** Response 200, status=null.

##### Test 6: `test_update_form_not_found`
- **Act:** `PUT /form/nonexistent` with `{ "name": "Jane" }`
- **Assert:** Response 404.

##### Test 7: `test_update_form_empty_body`
- **Setup:** Create a chat + FormSubmission (name="John", email="john@test.com").
- **Act:** `PUT /form/{form_id}` with `{}`
- **Assert:** Response 200, all fields unchanged.

##### Test 8: `test_delete_form`
- **Setup:** Create a chat + FormSubmission.
- **Act:** `DELETE /form/{form_id}`
- **Assert:** Response 200, returned form matches. Subsequent `GET` confirms deletion.

##### Test 9: `test_delete_form_not_found`
- **Act:** `DELETE /form/nonexistent`
- **Assert:** Response 404.

##### Test 10: `test_delete_form_idempotency`
- **Setup:** Create a chat + FormSubmission.
- **Act:** `DELETE /form/{form_id}` twice.
- **Assert:** First returns 200, second returns 404.

##### Test 11: `test_get_chat_forms_filter_by_status`
- **Setup:** Create a chat + 3 FormSubmissions: status=1, status=2, status=3.
- **Act:** `GET /chat/{chat_id}/forms?status=2`
- **Assert:** Response has 1 form with status=2.

##### Test 12: `test_get_chat_forms_filter_no_match`
- **Setup:** Create a chat + FormSubmission with status=1.
- **Act:** `GET /chat/{chat_id}/forms?status=3`
- **Assert:** Response == `[]`.

##### Test 13: `test_get_chat_forms_no_filter`
- **Setup:** Create a chat + 3 FormSubmissions with different statuses.
- **Act:** `GET /chat/{chat_id}/forms` (no status param)
- **Assert:** All 3 returned.

#### Chat Bot Tool Tests

##### Test 14: `test_update_form_via_chat`
- **Setup:** Create a chat + FormSubmission.
- **Mock:** OpenAI returns `update_form_submission` tool call with form_id and `{ "name": "Updated Name" }`.
- **Act:** `PUT /chat/{chat_id}` with user message.
- **Assert:** FormSubmission in DB has updated name. Tool response contains "Success".

##### Test 15: `test_update_form_via_chat_invalid_id`
- **Mock:** OpenAI returns `update_form_submission` with nonexistent form_id.
- **Act:** `PUT /chat/{chat_id}` with user message.
- **Assert:** Tool response contains "Error" and "not found". No DB changes.

##### Test 16: `test_delete_form_via_chat`
- **Setup:** Create a chat + FormSubmission.
- **Mock:** OpenAI returns `delete_form_submission` tool call with form_id.
- **Act:** `PUT /chat/{chat_id}` with user message.
- **Assert:** FormSubmission deleted from DB. Tool response contains "Success".

##### Test 17: `test_delete_form_via_chat_invalid_id`
- **Mock:** OpenAI returns `delete_form_submission` with nonexistent form_id.
- **Act:** `PUT /chat/{chat_id}` with user message.
- **Assert:** Tool response contains "Error" and "not found".

##### Test 18: `test_update_form_via_chat_invalid_status`
- **Setup:** Create a chat + FormSubmission.
- **Mock:** OpenAI returns `update_form_submission` with `{ "form_id": "...", "status": 99 }`.
- **Act:** `PUT /chat/{chat_id}` with user message.
- **Assert:** Tool response contains "Error". FormSubmission status unchanged in DB.

### Integration Test (manual)
1. Start backend + frontend.
2. Create a chat, submit a form: "Submit an interest form for John Doe, john@test.com, 555-1234".
3. Note the form ID in the assistant response.
4. Ask: "Update form {id} — change the name to Jane Smith and set status to 2."
5. Verify in DB that name and status are updated.
6. Ask: "Delete form {id}."
7. Verify in DB that the form is deleted.
8. Test REST endpoints via `/docs`:
   - `PUT /form/{id}` with status=5 → 422
   - `PUT /form/{id}` with status=2 → 200
   - `DELETE /form/{id}` → 200
   - `GET /chat/{chat_id}/forms?status=2` → filtered results

---

## Files Modified

| File | Change |
|---|---|
| `backend/schemas.py` | Add `@field_validator("status")` to `FormSubmissionUpdate` and `FormSubmissionCreate`. Import `field_validator`. |
| `backend/main.py` | Extract `TOOLS` constant with all 3 tool definitions. Add `update_form_submission` and `delete_form_submission` handlers in tool_calls loop. Add `PUT /form/{form_id}` endpoint. Add `DELETE /form/{form_id}` endpoint. Add `status` query param to `GET /chat/{chat_id}/forms`. Update `SYSTEM_TEMPLATE`. Replace inline tools arrays with `TOOLS`. Import `Optional` from typing. |

**No model or migration changes needed for R2.** The `status` column already exists as `Integer` on `FormSubmission`.

---

## Definition of Done

### Deliverable A: Chat Bot Augmentation
- [ ] `TOOLS` constant defined with all 3 tool definitions (submit, update, delete)
- [ ] Both OpenAI calls use `TOOLS` instead of inline arrays
- [ ] `SYSTEM_TEMPLATE` updated with tool usage instructions
- [ ] `update_form_submission` tool handler: parses args, validates form_id, updates form via `crud.form.update()`
- [ ] `delete_form_submission` tool handler: parses args, validates form_id, deletes form via `crud.form.remove()`
- [ ] Error handling for: missing form_id, nonexistent form, malformed JSON, invalid status, generic exceptions
- [ ] All chat bot tool tests pass (Tests 14-18)

### Deliverable B: REST API
- [ ] `PUT /form/{form_id}` endpoint — updates name, email, phone_number, status
- [ ] `DELETE /form/{form_id}` endpoint — deletes form, returns deleted form
- [ ] `GET /chat/{chat_id}/forms` — accepts optional `status` query parameter for filtering
- [ ] Status validation on `FormSubmissionUpdate`: only None, 1, 2, 3 allowed
- [ ] Status validation on `FormSubmissionCreate`: only None, 1, 2, 3 allowed (consistency)
- [ ] 404 returned for nonexistent form on PUT and DELETE
- [ ] 422 returned for invalid status values
- [ ] All REST API tests pass (Tests 1-13)

### Overall
- [ ] All 18 unit tests pass
- [ ] Manual integration test passes
- [ ] No regressions on existing R1 tests
- [ ] Logging covers all new operations
