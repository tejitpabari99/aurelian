# R1 — Save FormSubmission on Tool Call

## Requirement Summary

When the OpenAI model invokes the `submit_interest_form` tool during a chat, parse the tool call arguments and persist a `FormSubmission` row to the database, linked to the current chat via `chat_id`.

---

## Current State

### File: `backend/main.py` — `PUT /chat/{chat_id}` endpoint

The existing flow:

```
1. Fetch chat from DB by chat_id
2. Send messages to OpenAI (with submit_interest_form tool definition)
3. Append assistant response to messages
4. IF assistant response contains tool_calls:
   a. For each tool call `t`:
      - Append a tool response message: { tool_call_id, role: "tool", name, content: "Success" }
      ❌ Does NOT parse t["function"]["arguments"]
      ❌ Does NOT save anything to DB
   b. Call OpenAI again with updated messages (including tool responses)
   c. Append second assistant response
5. Update chat in DB with final messages
```

### What's available but unused
- `crud.form` — `CRUDFormSubmission` instance with `.create()`, `.get()`, `.get_multi()`, `.update()`, `.remove()`
- `schemas.FormSubmissionCreate` — Pydantic model: `name: str, phone_number: str, email: str, chat_id: str, status: Optional[int] = None`
- `models.FormSubmission` — SQLAlchemy model with all columns, FK to `chat.id`

### Tool call structure from OpenAI

Each tool call `t` in `resp_message["tool_calls"]` looks like:

```json
{
  "id": "call_abc123",
  "type": "function",
  "function": {
    "name": "submit_interest_form",
    "arguments": "{\"name\": \"John Doe\", \"email\": \"john@example.com\", \"phone_number\": \"555-1234\"}"
  }
}
```

**Key detail:** `t["function"]["arguments"]` is a **JSON string**, not a dict. Must be parsed with `json.loads()`.

---

## Changes Required

### File: `backend/main.py`

#### 1. Add imports

```python
import json
import logging

logger = logging.getLogger(__name__)
```

#### 2. Modify the tool_calls processing block

**Location:** Inside the `if resp_message.get('tool_calls'):` block, within the `for t in resp_message["tool_calls"]:` loop.

**Before (current code):**
```python
for t in resp_message["tool_calls"]:
    data.messages.append(
        {
            "tool_call_id": t["id"],
            "role": "tool",
            "name": t["function"]["name"],
            "content": "Success",
        }
    )
```

**After (new code):**
```python
for t in resp_message["tool_calls"]:
    tool_name = t["function"]["name"]
    tool_content = "Success"

    if tool_name == "submit_interest_form":
        try:
            args = json.loads(t["function"]["arguments"])

            form_data = schemas.FormSubmissionCreate(
                name=args.get("name", ""),
                email=args.get("email", ""),
                phone_number=args.get("phone_number", ""),
                chat_id=chat_id,
            )

            created_form = await crud.form.create(db=db, obj_in=form_data)

            logger.info(
                "FormSubmission created: id=%s, chat_id=%s, name=%s",
                created_form.id, chat_id, form_data.name,
            )
            tool_content = f"Success. Form submission ID: {created_form.id}"

        except json.JSONDecodeError as e:
            logger.error("Failed to parse tool call arguments: %s", e)
            tool_content = f"Error: Could not parse form data — {e}"
        except Exception as e:
            logger.error("Failed to create FormSubmission: %s", e, exc_info=True)
            tool_content = f"Error: Failed to save form — {e}"

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

## Detailed Behavior Specification

### Happy Path
1. User asks to submit an interest form in the chat.
2. OpenAI collects name, email, phone_number via conversation.
3. OpenAI issues a `submit_interest_form` tool call with arguments JSON.
4. Backend parses arguments, creates `FormSubmission` row.
5. Tool response content = `"Success. Form submission ID: {id}"`.
6. OpenAI receives the success response and generates a confirmation message to the user.
7. Chat messages (including tool call + tool response) are saved to DB.

### Multiple Tool Calls in One Response
- OpenAI can issue multiple tool calls in a single response.
- The existing `for` loop already iterates over all of them.
- Each `submit_interest_form` call creates its own separate `FormSubmission` row.
- Other tool names (if any in the future) are handled by the fallback — they get `"Success"` content without DB write.

---

## Edge Cases

| # | Case | Expected Behavior |
|---|---|---|
| 1 | `arguments` is malformed JSON | Catch `json.JSONDecodeError`, log error, set tool content to error message. OpenAI will relay the error to the user. |
| 2 | `arguments` is valid JSON but missing fields (e.g., no `email`) | `args.get("email", "")` returns empty string. `FormSubmissionCreate` accepts it (fields are `str`, not validated for format). Form is created with empty field. **Assumption:** we accept partial data rather than rejecting — the LLM should have collected all fields, but we're permissive at the DB layer. |
| 3 | `chat_id` doesn't exist in DB | `crud.form.create()` will fail on FK constraint. Caught by the generic `except Exception`. Tool content set to error. |
| 4 | DB is down / connection error | Caught by generic `except Exception`. Error logged with `exc_info=True`. Tool content set to error. |
| 5 | Tool call is for a different function (not `submit_interest_form`) | The `if tool_name == "submit_interest_form"` guard skips it. Tool content remains `"Success"`. This is forward-compatible with Task 2 where new tools will be added. |
| 6 | `arguments` contains extra unexpected fields | `args.get()` only picks the fields we need. Extra fields are silently ignored. |
| 7 | Multiple form submissions in one response | Each creates its own row. All are linked to the same `chat_id`. Each gets its own tool response. |

---

## Logging Specification

| Level | When | Message Format |
|---|---|---|
| `INFO` | Form created successfully | `"FormSubmission created: id=%s, chat_id=%s, name=%s"` |
| `ERROR` | JSON parse failure | `"Failed to parse tool call arguments: %s"` |
| `ERROR` | Any other exception during creation | `"Failed to create FormSubmission: %s"` (with `exc_info=True` for full traceback) |

Configure logger at module level:
```python
import logging
logger = logging.getLogger(__name__)
```

---

## Testing Plan

### Unit Tests (file: `backend/tests/test_r1_form_submission.py`)

#### Test 1: `test_form_created_on_tool_call`
- **Setup:** Create a chat in DB. Mock `openai_client.chat.completions.create` to return a response with a `submit_interest_form` tool call (name="Jane", email="jane@test.com", phone="555-0001"), then on second call return a normal assistant message.
- **Act:** `PUT /chat/{chat_id}` with messages `[{"role": "user", "content": "Submit form for Jane"}]`
- **Assert:**
  - Response status 200
  - A `FormSubmission` row exists in DB with name="Jane", email="jane@test.com", phone_number="555-0001", chat_id=chat_id
  - Response messages contain the tool call and tool response with "Success" in content

#### Test 2: `test_form_created_with_partial_args`
- **Setup:** Mock OpenAI to return tool call with only `name` in arguments (no email, no phone).
- **Assert:** FormSubmission created with name="Jane", email="", phone_number=""

#### Test 3: `test_form_creation_handles_malformed_json`
- **Setup:** Mock OpenAI to return tool call with `arguments = "not valid json"`.
- **Assert:**
  - No FormSubmission row created
  - Tool response content contains "Error"
  - Endpoint does NOT return 500 — it continues gracefully

#### Test 4: `test_multiple_tool_calls_create_multiple_forms`
- **Setup:** Mock OpenAI to return 2 tool calls in one response.
- **Assert:** 2 FormSubmission rows created, each with correct data.

#### Test 5: `test_non_form_tool_call_ignored`
- **Setup:** Mock OpenAI to return a tool call with `name: "some_other_tool"`.
- **Assert:** No FormSubmission created. Tool response is `"Success"`.

### Integration Test (manual or scripted)
1. Start backend + frontend
2. Create a new chat
3. Type: "I'd like to submit an interest form. Name: John Doe, Email: john@doe.com, Phone: 555-1234"
4. Verify in DB (`SELECT * FROM form_submission`) that a row exists with correct data
5. Verify chat messages include the tool call and "Success" response

---

## Metrics (Future — not blocking for this change)

| Metric | Type | Description |
|---|---|---|
| `form_submission.created.count` | Counter | Incremented on each successful FormSubmission creation |
| `form_submission.created.error.count` | Counter | Incremented on each failed creation attempt |
| `form_submission.created.latency_ms` | Histogram | Time from parsing args to DB commit returning |

---

## Validation Notes

- **No email format validation** at this stage. The LLM is the "validator" — it collects what the user provides. We store as-is. Format validation can be added later via Pydantic `EmailStr` if needed.
- **No phone format validation.** Same rationale.
- **`status` defaults to `None`** on creation. This is by design — new form submissions have no status until explicitly set (Task 2 scope).

---

## Files Modified

| File | Change |
|---|---|
| `backend/main.py` | Add `import json, logging`. Add form creation logic inside tool_calls loop. Add `if tool_name ==` guard for forward-compatibility. |

**No schema, model, or migration changes needed for R1.** Everything required already exists.

---

## Definition of Done

- [ ] `submit_interest_form` tool call creates a `FormSubmission` row in the DB
- [ ] Tool response includes the created form's ID
- [ ] Errors are caught, logged, and returned as tool content (no 500s)
- [ ] Multiple tool calls in one response each create their own form
- [ ] Non-form tool calls are unaffected
- [ ] All 5 unit tests pass
- [ ] Manual integration test passes
