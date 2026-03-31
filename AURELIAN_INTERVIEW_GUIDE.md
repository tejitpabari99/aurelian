# Aurelian Technical Interview Guide

## 1. Executive Summary

`Aurelian` is a small full-stack AI chat application built as a take-home assessment. The starting point was a basic chat UI backed by a FastAPI service that forwards messages to OpenAI and stores chats in SQLite.

The assignment asked the candidate to evolve that prototype into a system that can:

1. Collect structured interest forms through LLM tool calling.
2. Persist those forms in the database and display them in the UI.
3. Support updating and deleting forms through both chat tools and REST APIs.
4. Design and then implement a reusable change-history system for revision tracking.

The repo now goes beyond the original minimum:

- Form submissions are stored and shown alongside chats.
- Forms can be edited and deleted from the chat UI.
- The chatbot can also update and delete forms via tools.
- A generic `change_history` model and API exist.
- Chat deletion cascades to form deletion and records history.
- Backend and frontend validation were added.
- The frontend is being adjusted locally to call the backend through Next.js `/api/*` rewrites instead of hardcoded `localhost:8000` URLs.

If you need one sentence for an interview:

> Aurelian is an AI-assisted CRM-style intake workflow where a chat agent collects lead/contact interest forms, stores them, lets users manage them, and tracks how those records changed over time.

---

## 2. What Problem This Project Solves

The business problem is not “build ChatGPT.” The real problem is:

- A user interacts conversationally.
- The AI extracts structured data from that conversation.
- The system persists that data as a normal business record.
- Operators or users need to see, update, filter, delete, and audit those records.

That makes this app closer to:

- lead capture
- intake/triage workflow
- lightweight operations CRM
- support/request tracking with AI-assisted data collection

The important technical shift is from **unstructured conversation** to **structured system state**.

---

## 3. Assignment Scope and How the Repo Evolved

### Original take-home requirements from `README.md`

### Task 1

- When the model calls `submit_interest_form`, create a `FormSubmission` row.
- Show submitted forms in the chat UI.

### Task 2

- Allow updating and deleting forms via chat tools.
- Add REST endpoints to update, list, filter, and delete forms.
- Validate `status` so it is one of `None`, `1`, `2`, `3`.

### Task 3

- Design a generic revision-history model in `task3.md`.
- Explain how it would track field changes, before/after values, and timestamps.

### What the current repo actually contains

- Task 1 implementation
- Task 2 implementation
- Task 3 design document
- Task 3 implementation, including migration, model, service layer, endpoints, and frontend history modal
- extra validation improvements
- chat deletion support

So in interview terms: the project started as a narrowly scoped assessment but was extended into a more complete, auditable CRUD workflow.

---

## 4. Stack Overview

### Backend

- FastAPI
- SQLAlchemy async ORM
- SQLite via `aiosqlite`
- Alembic for schema migrations
- OpenAI Python SDK
- Pydantic v2 for request/response validation
- pytest + httpx for backend tests

### Frontend

- Next.js 14 App Router
- React 18
- TypeScript
- Tailwind CSS
- SWR for read-side data fetching

### Persistence

- `backend/dev.db` is the local SQLite database file.

### Core architectural idea

- Backend owns system-of-record data.
- OpenAI is used only for chat generation and tool decisions.
- Frontend is thin and directly maps UI actions to backend endpoints.

---

## 5. End-to-End System Flow

### Chat creation

1. Frontend home page calls `POST /chat`.
2. Backend creates a `Chat` row with empty `messages`.
3. Frontend navigates to `/{chatId}`.

### Normal chat message flow

1. User enters text in `frontend/app/[chatId]/page.tsx`.
2. Frontend sends `PUT /chat/{chat_id}` with the full message list.
3. Backend prepends a system prompt and sends the conversation to OpenAI.
4. OpenAI returns either:
   - a normal assistant message, or
   - an assistant message with `tool_calls`.
5. Backend appends the assistant message to chat history.
6. If tools were called, backend executes them, appends tool response messages, then calls OpenAI again so the assistant can produce a user-facing follow-up reply.
7. Backend persists the updated message transcript on the `chat` row.
8. Backend re-fetches the chat with related forms and returns it.

### Form creation flow

1. OpenAI calls `submit_interest_form`.
2. Backend parses `tool_call.function.arguments` JSON.
3. Backend validates via `schemas.FormSubmissionCreate`.
4. Backend inserts `form_submission`.
5. Backend records a `change_history` row with event type `created`.
6. Backend returns a tool success string containing the form ID.

### Form update flow

This works in two paths:

- via chat tool `update_form_submission`
- via REST `PUT /form/{form_id}`

Both paths:

1. load the form
2. snapshot old values
3. validate update payload
4. persist changes
5. compute diff
6. write `change_history` row if anything actually changed

### Form delete flow

This also works in two paths:

- via chat tool `delete_form_submission`
- via REST `DELETE /form/{form_id}`

Both paths:

1. load the form
2. snapshot old values
3. delete the form
4. record deletion history

### Chat deletion flow

1. Frontend home page calls `DELETE /chat/{chat_id}`.
2. Backend eager-loads the chat and related forms.
3. Backend records deletion history for each attached form.
4. Backend deletes the chat.
5. SQLAlchemy cascade deletes the related forms.

---

## 6. Data Model

There are three main entities.

### `Chat`

Represents one conversation thread.

Fields:

- `id: str`
- `created_at: datetime`
- `messages: JSON`
- `form_submissions: relationship`

Why `messages` is JSON:

- It stores OpenAI-style conversational payloads directly.
- That keeps the prototype simple.
- Tradeoff: message querying is poor because it is not normalized.

### `FormSubmission`

Represents structured user interest data collected through the chat.

Fields:

- `id: str`
- `created_at: datetime`
- `chat_id: str`
- `name: str`
- `phone_number: str`
- `email: str`
- `status: int | None`

Domain meaning of `status`:

- `None`: not set
- `1`: TO DO
- `2`: IN PROGRESS
- `3`: COMPLETED

Important detail:

- `TRACKED_FIELDS = ("name", "phone_number", "email", "status")`
- This drives diff generation for audit history.

### `ChangeHistory`

Generic audit/event table for mutable entities.

Fields:

- `id: str`
- `created_at: datetime`
- `entity_type: str`
- `entity_id: str`
- `revision: int`
- `event_type: str`
- `changes: JSON | None`
- `change_source: str | None`

Example `changes` payload:

```json
{
  "status": { "old": 1, "new": 2 },
  "email": { "old": "old@test.com", "new": "new@test.com" }
}
```

Why this design matters:

- reusable across entity types
- compact
- preserves value types in JSON
- answers “what changed” directly

Tradeoff:

- no DB-level foreign key from history to every possible entity type

---

## 7. How the Backend Works

## `backend/database.py`

Purpose:

- creates the async SQLAlchemy engine and session factory
- defines declarative `Base`

Key interview points:

- Uses `sqlite+aiosqlite:///./dev.db`.
- Backend ORM code is async.
- Alembic uses a separate sync connection path in `alembic/env.py`.

## `backend/models.py`

Purpose:

- SQLAlchemy table definitions

Important relationships:

- `Chat.form_submissions` uses cascade delete.
- `FormSubmission.chat_id` is a foreign key to `chat.id`.
- `ChangeHistory` is intentionally generic and polymorphic.

Likely interview questions:

- Why not normalize messages into a `chat_message` table?
- Why no foreign key from `change_history`?
- Why track only specific form fields?

## `backend/schemas.py`

Purpose:

- Pydantic request/response contracts
- validation rules

Important schema groups:

- `Chat`, `ChatCreate`, `ChatUpdate`
- `FormSubmission`, `FormSubmissionCreate`, `FormSubmissionUpdate`
- `ChangeHistory`, `ChangeHistoryCreate`

Validation added:

- email regex
- phone regex
- name constraints and script/injection rejection
- status enum-like validation

Subtle point:

- `FormSubmissionUpdate` uses optional fields so partial updates are possible.
- `crud.update()` respects `exclude_unset=True`, so omitted fields are not overwritten.

## `backend/crud.py`

Purpose:

- generic CRUD layer reused across models

Important behaviors:

- `create()` stamps `created_at`
- `update()` copies only supplied fields
- `remove()` deletes and commits immediately

Interview angle:

- This is intentionally thin. Business logic is mostly in `main.py` and `change_tracker.py`, not the CRUD layer.

## `backend/change_tracker.py`

Purpose:

- encapsulates all history logic

Main responsibilities:

- compute next revision number
- serialize values safely to JSON-compatible types
- compute diffs across tracked fields
- record create/update/delete events
- retrieve ordered history

Key design decision:

- `record_update()` skips writes when nothing changed

That is important because:

- empty update requests should not create fake revisions
- UI “save without changes” should not pollute audit history

## `backend/main.py`

This is the central orchestration layer.

It handles:

- API route definitions
- OpenAI tool definitions
- LLM/tool orchestration
- DB reads and writes
- history recording

### Core constants

- `SYSTEM_TEMPLATE`: instructs the LLM which tools exist and when to ask for a form ID
- `TOOLS`: OpenAI function definitions for create/update/delete form actions

### Main backend endpoints

- `GET /`
- `GET /chat`
- `POST /chat`
- `PUT /chat/{chat_id}`
- `DELETE /chat/{chat_id}`
- `GET /chat/{chat_id}`
- `GET /chat/{chat_id}/forms`
- `GET /form/{form_id}/history`
- `GET /history/{entity_type}/{entity_id}`
- `PUT /form/{form_id}`
- `DELETE /form/{form_id}`

### Most important endpoint: `PUT /chat/{chat_id}`

Why it matters:

- It is both chat controller and AI tool runner.

Flow inside this endpoint:

1. load chat
2. call OpenAI
3. append assistant message
4. inspect `tool_calls`
5. run business logic for each tool
6. append tool result messages
7. call OpenAI again for final assistant reply
8. update chat transcript in DB
9. return hydrated chat with forms

This is the highest-value file to understand for interviews.

---

## 8. How the Frontend Works

The frontend is intentionally simple: one home page and one chat page.

## `frontend/app/page.tsx`

Purpose:

- lists chats
- creates chats
- deletes chats

Important flow:

- uses `useSWR({ url: 'chat' }, fetcher)` for list loading
- uses `POST /api/chat` to create
- uses `DELETE /api/chat/{id}` to delete

## `frontend/app/[chatId]/page.tsx`

This is the main UI.

Responsibilities:

- load one chat
- render messages
- send new messages
- display related forms
- filter forms by status
- edit/delete forms through REST
- show change-history modal

Internal UI pieces in the same file:

- `ChangeHistoryPanel`
- `ToolCallComponent`
- `ToolResponseComponent`
- `OpenAIConversationDisplay`
- `FormCard`
- `FormSubmissionsPanel`

Important state:

- `input`
- `messages`
- `formSubmissions`
- `statusFilter`

Important behavior:

- User-facing chat display hides assistant tool-call-only messages and hides raw tool response messages.
- The forms side panel is the real CRUD surface for structured data.
- History is fetched lazily only when the user opens the modal.

Important implementation detail:

- `refreshForms()` uses the status filter and re-queries `/chat/{chatId}/forms`.
- After send/update/delete operations, the page refreshes forms rather than trusting stale local state.

## `frontend/utils/fetcher.ts`

Purpose:

- small shared SWR fetch helper

Current local change:

- it now fetches from `/api/...` instead of hardcoded `http://localhost:8000/...`

Why that matters:

- avoids hardcoding origin
- works better with same-origin frontend deployment
- uses Next.js rewrite proxying

## `frontend/app/layout.tsx`

Purpose:

- global page shell
- imports Inter font and `globals.css`

## `frontend/app/globals.css`

Purpose:

- Tailwind imports
- custom scrollbar styling

Note:

- Tailwind directives are duplicated twice. That is harmless but messy.

## `frontend/next.config.mjs`

Purpose:

- currently defines rewrites from `/api/:path*` to `http://127.0.0.1:8000/:path*`

This is part of the latest local uncommitted changes and is effectively a frontend proxy layer.

---

## 9. What Alembic Is

Alembic is the database migration tool used with SQLAlchemy.

Plain explanation:

- SQLAlchemy models describe the desired schema in Python.
- Alembic records schema changes over time as migration scripts.
- Those scripts let a database evolve from one version to the next in a controlled order.

Without Alembic:

- every developer would manually edit the database
- schema drift would happen
- deployments would be inconsistent

With Alembic:

- schema changes are versioned in source control
- you can upgrade a DB to the latest schema with `alembic upgrade head`
- you can see exactly when tables or columns were introduced

### Files involved here

#### `backend/alembic.ini`

- Alembic config file
- tells Alembic where migration scripts live

#### `backend/alembic/env.py`

- runtime bridge between Alembic and your SQLAlchemy metadata
- imports `Base.metadata`
- tells Alembic which schema objects exist

#### `backend/alembic/versions/546f84e030c3_create_tables.py`

- initial migration
- creates `chat` and `form_submission`

#### `backend/alembic/versions/a1b2c3d4e5f6_add_change_history_table.py`

- later migration
- adds `change_history`

### Why Alembic matters specifically in Aurelian

This repo has two schema eras:

1. initial chat + form tables
2. later audit/history support

Alembic captures that evolution. In interview terms, it proves the candidate understood that schema change should be:

- explicit
- reproducible
- source-controlled

### One nuance here

The runtime app uses an async DB engine, but Alembic uses a synchronous engine in `env.py`. That is normal. Migration tools do not need to match the async runtime path.

---

## 10. API Surface

### Chat APIs

- `GET /chat`
  - list chats
- `POST /chat`
  - create a new chat
- `GET /chat/{chat_id}`
  - fetch one chat plus related forms
- `PUT /chat/{chat_id}`
  - main chat/update endpoint
- `DELETE /chat/{chat_id}`
  - delete a chat and cascade its forms

### Form APIs

- `GET /chat/{chat_id}/forms`
  - list forms for one chat
  - optional `status` filter
- `PUT /form/{form_id}`
  - partial update for name/email/phone/status
- `DELETE /form/{form_id}`
  - delete a form

### History APIs

- `GET /form/{form_id}/history`
  - form-specific history
- `GET /history/{entity_type}/{entity_id}`
  - generic history lookup

---

## 11. Message and Data Shapes

## Chat messages

The `messages` field stores OpenAI-style message dicts.

Examples:

### User message

```json
{ "role": "user", "content": "Please submit my interest form" }
```

### Assistant message with tool call

```json
{
  "role": "assistant",
  "content": null,
  "tool_calls": [
    {
      "id": "call_123",
      "type": "function",
      "function": {
        "name": "submit_interest_form",
        "arguments": "{\"name\":\"Jane\",\"email\":\"jane@test.com\",\"phone_number\":\"555-1111\"}"
      }
    }
  ]
}
```

### Tool response message

```json
{
  "tool_call_id": "call_123",
  "role": "tool",
  "name": "submit_interest_form",
  "content": "Success. Form submission ID: abc123"
}
```

### Form submission payloads

Create/update data uses:

- `name`
- `email`
- `phone_number`
- `status`

### Change history payload

Each history row has:

- entity coordinates: `entity_type`, `entity_id`
- ordering: `revision`, `created_at`
- classification: `event_type`, `change_source`
- field diffs: `changes`

---

## 12. Validation Rules

Validation exists in both backend and frontend.

### Backend validation

In `backend/schemas.py`:

- email must match a conventional email regex
- phone must be 7-20 chars and use allowed phone symbols
- name must be non-empty, max 200 chars, and reject obvious script-like content
- status must be one of `None`, `1`, `2`, `3`

### Frontend validation

In `frontend/app/[chatId]/page.tsx`:

- matching client-side regex checks for edit form UX
- inline field errors
- red borders for invalid fields

Why dual validation is good:

- frontend gives immediate UX feedback
- backend remains the final source of truth

---

## 13. Tests and Verification

## Backend tests present

### `backend/tests/conftest.py`

- creates isolated in-memory SQLite DB
- overrides FastAPI dependency injection for tests
- provides OpenAI response mocks

### `backend/tests/test_r1_form_submission.py`

Tests:

- form created on tool call
- malformed JSON handling
- validation failure behavior
- multiple tool calls
- non-form tool call ignored

### `backend/tests/test_r2_form_crud.py`

Tests:

- REST form update
- valid and invalid status values
- empty update body
- delete behavior
- idempotent delete behavior
- list forms with and without status filter
- multi-field updates
- chat-tool update/delete flows
- change-history recording expectations

## Verification I ran

- `frontend`: `npm run build` succeeded
- `backend`: `pytest -q` could not run in this environment because `pytest` is not installed globally

That means frontend build health is confirmed, but backend tests are only inspectable, not re-executed here without installing dependencies.

---

## 14. Commit and Change History of the Project

Recent commits:

- `9992615` `current state`
- `a0bdbc1` `R2`
- `e97ce8d` `R3`
- `a5c0b7e` `Task 3`
- `2ff675f` `Additional minor changes`

### What changed in each phase

#### `9992615 current state`

- baseline starter project

#### `a0bdbc1 R2`

Large implementation pass:

- extended backend APIs
- added extensive tests
- added frontend forms panel and edit/delete UX
- added requirements docs for R2

#### `e97ce8d R3`

- added `changes/R3-requirements.md`
- added `task3.md` design document

#### `a5c0b7e Task 3`

- implemented actual change-history system
- added migration, model, service, schema updates, endpoints, and frontend history modal

#### `2ff675f Additional minor changes`

- added validation hardening
- added delete-chat feature
- updated related tests and docs

This is a strong interview point:

> The repo shows a progression from requirements documentation, to feature implementation, to auditability, to hardening and UX improvements.

---

## 15. Current Local Uncommitted Changes

The working tree is currently dirty on this branch before this guide was added.

Modified files:

- `backend/dev.db`
- `frontend/app/[chatId]/page.tsx`
- `frontend/app/page.tsx`
- `frontend/next.config.mjs`
- `frontend/package-lock.json`
- `frontend/utils/fetcher.ts`

### What those current changes do

They mainly shift the frontend from direct backend calls like:

- `http://localhost:8000/chat`

to same-origin calls like:

- `/api/chat`

paired with a Next.js rewrite:

- `/api/:path* -> http://127.0.0.1:8000/:path*`

Interpretation:

- This is a deployment/ergonomics cleanup.
- It reduces hardcoded origins in the client.
- It lets the browser talk to Next, and Next proxy to FastAPI.
- It likely improves local dev consistency and avoids some cross-origin issues.

`frontend/package-lock.json` has incidental lockfile metadata changes, and `backend/dev.db` changed as a generated artifact.

If asked “what changes did you make?” in a real interview, separate the answers into:

1. committed product changes across R1/R2/R3
2. current local integration cleanup around frontend API routing

---

## 16. File-by-File Walkthrough

This section is for “tell me what each file does.”

### Root

- `README.md`
  - take-home instructions, setup, task definitions
- `task3.md`
  - design rationale for change history
- `create_zip.py`
  - packages tracked and untracked non-ignored files, plus `.git`, into timestamped zips
- `.gitignore`
  - Python/general ignores, plus `zips/*`

### `changes/`

- `changes-overview.md`
  - maps tasks to implementation phases
- `R1-requirements.md`
  - detailed spec for task 1 behavior
- `R2-requirements.md`
  - detailed spec for task 2 behavior
- `R3-requirements.md`
  - detailed design expectations for task 3
- `additional.md`
  - documents post-task improvements

### `backend/`

- `requirements.txt`
  - Python dependency lock list
- `pytest.ini`
  - pytest config and import path setup
- `CONTEXT.md`
  - high-level backend orientation
- `database.py`
  - DB engine/session/Base
- `models.py`
  - SQLAlchemy models
- `schemas.py`
  - Pydantic contracts and validation
- `crud.py`
  - generic CRUD layer
- `change_tracker.py`
  - history service logic
- `main.py`
  - FastAPI app and all endpoint orchestration
- `dev.db`
  - local SQLite database file

### `backend/alembic/`

- `README`
  - basic Alembic template note
- `env.py`
  - migration environment bootstrap
- `script.py.mako`
  - migration template used when generating new revisions
- `versions/546f84e030c3_create_tables.py`
  - initial schema migration
- `versions/a1b2c3d4e5f6_add_change_history_table.py`
  - audit-history migration

### `backend/tests/`

- `__init__.py`
  - package marker
- `conftest.py`
  - shared fixtures and OpenAI mocks
- `test_r1_form_submission.py`
  - task 1 tests
- `test_r2_form_crud.py`
  - task 2 and history tests

### `frontend/`

- `package.json`
  - JS dependencies and scripts
- `package-lock.json`
  - npm lockfile
- `tsconfig.json`
  - TypeScript config
- `.eslintrc.json`
  - Next.js lint config
- `.gitignore`
  - frontend-specific ignores
- `CONTEXT.md`
  - high-level frontend orientation
- `next.config.mjs`
  - Next config and current rewrite proxy
- `postcss.config.mjs`
  - PostCSS/Tailwind setup
- `tailwind.config.ts`
  - Tailwind content scanning and theme extension
- `utils/fetcher.ts`
  - SWR fetch helper

### `frontend/app/`

- `layout.tsx`
  - root layout
- `globals.css`
  - Tailwind imports and scrollbar styling
- `page.tsx`
  - chat list page
- `[chatId]/page.tsx`
  - main chat and forms management UI
- `favicon.ico`
  - app icon

### `frontend/public/`

- `next.svg`
  - default Next.js asset
- `vercel.svg`
  - default Vercel asset

---

## 17. Architecture Strengths

- Clear separation between chat transcript and structured records
- Thin generic CRUD layer, leaving business logic explicit
- Good use of Pydantic validation
- Change-history logic centralized instead of duplicated in endpoints
- Tests use dependency override and OpenAI mocking, which is the right strategy
- Frontend stays simple and task-oriented

---

## 18. Architectural Weaknesses and Tradeoffs

These are likely interview discussion points.

### Chat transcript stored as one JSON blob

Pros:

- simple
- flexible

Cons:

- hard to query/search messages
- inefficient for large chats
- mixed concerns: transcript and domain actions coexist in one blob

### Business logic concentrated in `main.py`

Pros:

- easy to follow in a small project

Cons:

- endpoint file grows quickly
- harder to test fine-grained orchestration separately
- service layer boundaries are limited

### LLM-dependent workflows

Pros:

- natural-language collection experience

Cons:

- relies on prompt/tool quality
- needs defensive validation because model output is not trusted

### Generic change history without foreign keys

Pros:

- reusable
- schema-stable for future entities

Cons:

- referential integrity is application-enforced, not DB-enforced

---

## 19. Likely Interview Questions and Good Answer Directions

### Why use tool calling here?

Because the app needs the model to convert free-form user intent into structured business actions with typed arguments.

### Why not let the frontend submit forms directly?

The assignment specifically tests AI-assisted structured extraction from chat. The frontend UI edit/delete surface is secondary.

### Why validate if the model already collected the data?

Because model output is untrusted input. Validation must still happen server-side.

### Why use JSON diff history instead of snapshots?

Because the main question is “what changed,” not just “what was the entire object state.”

### Why two OpenAI calls in `PUT /chat/{chat_id}`?

First call decides whether tools are needed. After tool results exist, a second call lets the assistant produce a final natural-language response informed by tool execution.

### Why does form history belong in a generic table?

Because the requirement explicitly says future entities may need revision tracking too.

### Why is there both REST CRUD and chat-tool CRUD?

They serve different interaction modes:

- REST for deterministic UI actions
- tool calls for conversational workflows

---

## 20. If Asked “What Would You Improve Next?”

Here are the highest-value next steps based on the current codebase and likely real use.

### 1. Normalize chat messages into a dedicated table

Reason:

- easier querying
- pagination
- analytics
- audit separation

### 2. Move orchestration logic out of `main.py`

Reason:

- chat controller is doing too much
- introduce service modules for:
  - chat orchestration
  - form service
  - history service
  - OpenAI adapter

### 3. Add auth and actor identity

Reason:

- `change_history` currently captures `change_source` but not `changed_by`
- a real system needs user identity and authorization

### 4. Improve error contracts and UX

Reason:

- frontend still uses `alert`
- better typed error rendering would improve maintainability

### 5. Add pagination and sorting for forms/history

Reason:

- current history fetch returns everything
- fine for assessment scale, not for production scale

### 6. Strengthen observability

Reason:

- add structured logs
- request IDs
- metrics around tool success/failure and LLM latency

### 7. Add integration tests with migrations

Reason:

- current tests create schema from metadata, not via Alembic upgrade path
- production confidence improves if migrations are exercised

### 8. Replace hardcoded OpenAI model/config

Reason:

- model and prompt config should be environment-driven

### 9. Add optimistic concurrency or revision checks

Reason:

- current update path can last-write-win silently
- change history records this, but does not prevent conflicting edits

### 10. Product direction: evolve this into an intake operations dashboard

Reason:

- the app already looks like a lead/intake workflow
- next logical features are assignment, notes, search, status boards, and notifications

---

## 21. Short “Interview Answer” Version

If you need to explain the whole system in under a minute:

> Aurelian is a FastAPI + Next.js chat app where an OpenAI-powered assistant can collect structured interest forms through tool calls. Chats are stored as JSON transcripts, while extracted forms are stored as relational records linked to a chat. The backend supports both conversational CRUD through tools and direct CRUD through REST endpoints. The project was extended with validation, filtering, deletion, and a generic `change_history` table that records field-level diffs for create, update, and delete events. Alembic manages the schema evolution from the original `chat` and `form_submission` tables to the later audit-history model.

---

## 22. Final Mental Model

Use this mental map when preparing:

- `Chat` is the conversation container.
- `messages` is the raw AI transcript.
- `FormSubmission` is the structured business record extracted from chat.
- `PUT /chat/{chat_id}` is the orchestrator that bridges LLM behavior to database writes.
- REST endpoints exist so the UI can operate deterministically without always going through the LLM.
- `ChangeHistory` turns mutable forms into auditable records.
- Alembic is the schema versioning system that made the DB evolution reproducible.

If you can explain those six points clearly, you understand the project at the right depth for a technical interview.
