# Task 1 — Changes Overview: Collect Structured Interest Form

## What the README Asks (Task 1)

Task 1 has **two deliverables**:

### Deliverable A: Persist form submissions to the database
Update the `update_chat` function in `main.py` so that when the OpenAI model invokes the `submit_interest_form` tool, the collected arguments (name, email, phone_number) are saved as a `FormSubmission` row in the database, linked to the current chat.

### Deliverable B: Display form submissions in the chat UI
Update the API and frontend so that when a user opens a chat, they see the chat messages **plus** a list of all form submissions created during that chat.

---

## What Currently Exists

| Layer | What's there | What's missing |
|---|---|---|
| **DB Model** | `FormSubmission` table with id, created_at, chat_id (FK), name, phone_number, email, status — fully migrated | Nothing, model is complete |
| **Schema** | `FormSubmissionCreate(name, phone_number, email, chat_id, status?)` already defined | Not used anywhere |
| **CRUD** | `crud.form.create(db, obj_in=...)` ready to go | Never called |
| **API (`PUT /chat/{chat_id}`)** | Tool calls are detected, iterated over, but only a hardcoded `"Success"` string is appended as the tool response | No parsing of `t["function"]["arguments"]`, no DB write |
| **API (GET)** | `GET /chat/{chat_id}` returns chat with messages only | No endpoint to get form submissions by chat_id; `Chat` schema doesn't include `form_submissions` |
| **Frontend** | Chat page displays messages by role | No UI for form submissions, no fetch call for them |

---

## Requirements (Task 1)

| ID | Title | Summary | Status |
|---|---|---|---|
| R1 | Save FormSubmission on tool call | Parse tool call args in `PUT /chat/{chat_id}`, create `FormSubmission` row in DB | ✅ Implemented |
| R1b | Expose form submissions in API | Add `form_submissions` to `GET /chat/{chat_id}` response + dedicated `GET /chat/{chat_id}/forms` endpoint | ✅ Implemented |
| R1c | Display form submissions in chat UI | Show form submissions panel alongside chat messages on the chat page | Defined |

## Requirements (Task 2)

| ID | Title | Summary | Status |
|---|---|---|---|
| R2 | Update & Delete Form Submissions | Chat bot tools + REST API for update/delete form submissions, status validation, status filtering | Defined — see `R2-requirements.md` |

**Note:** R2 was originally scoped as "Expose form submissions in API" (Task 1 prerequisite). That work is now complete and merged into R1b. R2 has been repurposed to cover all of **Task 2** requirements: chat bot augmentation (update/delete tools), REST API endpoints (PUT, DELETE, GET with filtering), and status validation.

## Requirements (Task 3)

| ID | Title | Summary | Status |
|---|---|---|---|
| R3 | Change History Design | Design a generic, reusable data model for tracking the full revision history of Form Submissions (and future entities). Document what fields changed, old/new values, and when. Design-only — no code. Deliverable: `task3.md` | Defined — see `R3-requirements.md` |

---

## Implementation Phases

### Phase 1: Backend — Persist form submissions (R1)
**File:** `backend/main.py`
- Parse `t["function"]["arguments"]` (JSON string → dict)
- Create `FormSubmission` via `crud.form.create()`
- Error handling with try/except
- Logging for observability

### Phase 2: Backend — Expose in API (R2)
**Files:** `backend/schemas.py`, `backend/main.py`
- Add `form_submissions` to `schemas.Chat`
- Eager-load relationship in `GET /chat/{chat_id}`
- Add `GET /chat/{chat_id}/forms` endpoint

### Phase 3: Frontend — Display panel (R1c)
**File:** `frontend/app/[chatId]/page.tsx`
- Pull `form_submissions` from chat data
- Render `FormSubmissionsPanel` component
- Update state after each message exchange

### Phase 4: Change History Design (R3 — Task 3)
**File:** `task3.md` (project root)
- Design a generic, reusable data model for tracking revision history
- Document what fields changed, old/new values, and when
- Discuss design alternatives with pros/cons
- No code — design document only

### Phase 5: Quality
- Error handling, logging, input validation
- Unit & integration tests
- Metrics (future)

---

## Summary of File Changes

| File | Changes |
|---|---|
| `backend/main.py` | `import json`, parse tool args, `crud.form.create()`, add `/chat/{chat_id}/forms` endpoint, logging |
| `backend/schemas.py` | Add `form_submissions` to `Chat` response schema |
| `frontend/app/[chatId]/page.tsx` | Add form submissions state, `FormSubmissionsPanel` component, layout update |
| `task3.md` | **New file** — Change history data model design document (Task 3). No code. |
