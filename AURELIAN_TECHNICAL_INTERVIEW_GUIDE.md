# Aurelian Technical Interview Guide

## 1. What Aurelian Is

`Aurelian` is a small full-stack AI chat application built as a take-home assessment.

At the product level, it does two things:

1. It lets a user create a chat and exchange messages with an AI assistant.
2. It lets that assistant collect and manage structured "interest forms" during the conversation.

The project starts as a basic chatbot. The exercise then extends it into a system where:

- AI tool calls create `FormSubmission` records
- users can view those forms alongside the chat
- forms can be updated and deleted through both REST endpoints and the AI chat interface
- form changes are tracked in a generic change-history model

The repo is small, but it covers a lot of interview topics:

- FastAPI request handling
- SQLAlchemy async ORM usage
- schema validation with Pydantic
- Alembic migrations
- OpenAI tool-calling flow
- Next.js client-side data fetching
- full-stack state synchronization
- audit/history design

## 2. The Business Problem

The core problem is: "How do we turn free-form conversational intent into structured, editable business records?"

In this repo, the business record is an interest form with:

- `name`
- `email`
- `phone_number`
- `status`

The system needs to support a realistic workflow:

1. A user chats naturally.
2. The model decides to call a tool such as `submit_interest_form`.
3. The backend interprets the tool call and writes a real DB row.
4. The frontend shows those forms for the current chat.
5. Users or the AI can later update or delete those forms.
6. The system can explain how a form changed over time.

That makes Aurelian less like a pure chatbot and more like an AI-assisted workflow application.

## 3. High-Level Architecture

```text
User
  -> Next.js frontend
    -> FastAPI backend
      -> OpenAI chat completion API
      -> SQLite database via SQLAlchemy async ORM
      -> Alembic migrations for schema evolution
```

### Responsibilities by layer

| Layer | Responsibility |
|---|---|
| Frontend (`frontend/`) | Display chat list, chat detail page, forms panel, edit/delete UI, history modal |
| Backend (`backend/`) | Expose REST endpoints, call OpenAI, persist chats/forms/history, validate data |
| Database (`backend/dev.db`) | Store chats, forms, and change history |
| Migrations (`backend/alembic/`) | Create and evolve DB schema |
| Design/docs (`task3.md`, `changes/`, `CONTEXT.md`) | Explain requirements, history, and intended implementation |

## 4. End-to-End Runtime Flow

### 4.1 Create a chat

1. Frontend home page calls `POST /chat`.
2. Backend creates a `Chat` row with empty `messages`.
3. Frontend navigates to `/{chatId}`.

### 4.2 Send a chat message

1. Frontend appends the user message locally.
2. Frontend sends `PUT /chat/{chat_id}` with the full message array.
3. Backend loads the chat.
4. Backend sends messages plus `SYSTEM_TEMPLATE` plus tool definitions to OpenAI.
5. OpenAI returns either:
   - a normal assistant message, or
   - an assistant message containing `tool_calls`
6. Backend appends that assistant message to the chat transcript.
7. If tool calls exist, backend executes each tool call in Python.
8. Backend appends synthetic `role: "tool"` responses back into the message list.
9. Backend calls OpenAI a second time so the assistant can respond with a final natural-language answer after tool execution.
10. Backend stores the updated `messages`.
11. Backend returns the refreshed `Chat`, including `form_submissions`.

### 4.3 Create a form through AI

1. Model chooses `submit_interest_form`.
2. Backend parses `t["function"]["arguments"]` as JSON.
3. Backend builds `schemas.FormSubmissionCreate`.
4. Pydantic validates fields.
5. Backend writes `FormSubmission` via `crud.form.create(...)`.
6. Backend writes a `ChangeHistory` entry using `change_tracker.record_creation(...)`.
7. Backend returns a tool response that includes the created form ID.

### 4.4 Update or delete a form through AI

1. Model chooses `update_form_submission` or `delete_form_submission`.
2. Backend parses arguments and requires `form_id`.
3. Backend loads the target form.
4. For update:
   - snapshot old values
   - apply partial update
   - snapshot new values
   - write change history diff
5. For delete:
   - snapshot current values
   - delete row
   - write deletion history

### 4.5 Update or delete through REST UI

The frontend also calls direct REST endpoints:

- `PUT /form/{form_id}`
- `DELETE /form/{form_id}`
- `GET /chat/{chat_id}/forms`
- `GET /form/{form_id}/history`

That means the same domain object can be changed from two sources:

- `chat_tool`
- `rest_api`

The change history model explicitly captures that source.

## 5. Data Model

## 5.1 `Chat`

Defined in `backend/models.py`.

| Field | Type | Meaning |
|---|---|---|
| `id` | `String(32)` PK | Chat identifier |
| `created_at` | `DateTime` | Creation timestamp |
| `messages` | `JSON` | Full OpenAI-style conversation transcript |
| `form_submissions` | relationship | One-to-many forms for this chat |

### Why `messages` is JSON

The app stores the entire conversation in OpenAI-compatible message format, including:

- user messages
- assistant messages
- assistant tool call payloads
- tool response messages

This is pragmatic for a prototype because it avoids a normalized `message` table. Tradeoff: querying individual messages becomes harder.

## 5.2 `FormSubmission`

Defined in `backend/models.py`.

| Field | Type | Meaning |
|---|---|---|
| `id` | `String(32)` PK | Form identifier |
| `created_at` | `DateTime` | Form creation time |
| `chat_id` | FK -> `chat.id` | Parent chat |
| `name` | `String` | User name |
| `phone_number` | `String` | User phone |
| `email` | `String` | User email |
| `status` | `Integer` nullable | Workflow state |

### Status semantics

| Value | Meaning |
|---|---|
| `None` | unset |
| `1` | TO DO |
| `2` | IN PROGRESS |
| `3` | COMPLETED |

### `TRACKED_FIELDS`

`FormSubmission.TRACKED_FIELDS = ("name", "phone_number", "email", "status")`

This is important. It defines which fields participate in audit diff generation. That keeps history logic generic and prevents hard-coding the field list in multiple places.

## 5.3 `ChangeHistory`

Defined in `backend/models.py`.

| Field | Type | Meaning |
|---|---|---|
| `id` | `String(32)` PK | History row ID |
| `created_at` | `DateTime` | Time of change |
| `entity_type` | `String(64)` | Generic entity name, e.g. `form_submission` |
| `entity_id` | `String(32)` | ID of changed record |
| `revision` | `Integer` | Monotonic revision per entity |
| `event_type` | `String(16)` | `created`, `updated`, `deleted` |
| `changes` | `JSON` nullable | Field-level diff |
| `change_source` | `String(32)` nullable | `chat_tool`, `rest_api`, etc. |

### Why this model matters

This is the answer to Task 3. It is generic, append-only, and future-proof for other entity types.

Example `changes` payload:

```json
{
  "status": { "old": 1, "new": 2 },
  "email": { "old": "old@test.com", "new": "new@test.com" }
}
```

## 6. Validation Rules

Implemented in `backend/schemas.py`.

### Email

- regex-based validation
- expects a normal `user@domain.tld` shape

### Phone

- accepts digits, spaces, dashes, parentheses, optional leading `+`
- length 7-20

### Name

- cannot be empty
- max 200 chars
- rejects obvious script injection patterns

### Status

- only `None`, `1`, `2`, `3`

### Why validation is in Pydantic

This gives clean FastAPI `422` errors and keeps validation close to request schemas instead of scattering it across endpoint code.

## 7. Backend File-by-File Guide

## 7.1 `backend/main.py`

This is the main application entrypoint and the most important interview file.

### What it does

- creates the FastAPI app
- configures CORS
- initializes OpenAI client
- defines system prompt and tool schema
- provides all API endpoints
- coordinates DB access, OpenAI calls, tool handling, and change tracking

### Important objects

#### `SYSTEM_TEMPLATE`

Tells the assistant what it is allowed to do and how to behave around form IDs and statuses.

Interview angle:

- Why put this in backend instead of frontend?
- How could prompt drift affect tool use?

#### `TOOLS`

OpenAI function-calling schema for:

- `submit_interest_form`
- `update_form_submission`
- `delete_form_submission`

The backend is using the classic "LLM decides, backend executes" pattern.

### Endpoints

#### `GET /`

Simple health/demo endpoint.

#### `GET /chat`

- returns up to 10 chats
- eager-loads `form_submissions` using `selectinload`

Why eager loading matters:

- prevents lazy-loading problems in async response serialization
- avoids N+1 surprises during response generation

#### `POST /chat`

- creates a chat
- re-fetches it with forms eagerly loaded before returning

#### `PUT /chat/{chat_id}`

This is the most interviewable endpoint.

It does all of the following:

1. load chat
2. send current conversation to OpenAI
3. inspect tool calls
4. execute backend actions
5. append `role: "tool"` messages
6. make second OpenAI call
7. persist final chat transcript
8. return chat plus forms

##### Why there are two OpenAI calls

The first call asks: "Do you want to call a tool?"

The second asks: "Now that the tool result exists, what should the assistant say to the user?"

That is the standard tool-calling interaction loop.

##### Tool handler: `submit_interest_form`

- parses JSON args
- validates via `FormSubmissionCreate`
- creates row
- records history as `created`
- returns success message with form ID

##### Tool handler: `update_form_submission`

- requires `form_id`
- snapshots old values
- builds partial `update_fields` only from keys actually sent by model
- validates via `FormSubmissionUpdate`
- updates row
- records diff history

Important subtlety:

It intentionally avoids overwriting missing fields with `None`. That is good partial-update behavior.

##### Tool handler: `delete_form_submission`

- requires `form_id`
- snapshots old values
- removes row
- records deletion history

##### Failure modes handled

- malformed JSON
- validation errors
- missing `form_id`
- nonexistent form
- generic exceptions

The tool responses are written back into the transcript, so the model can react to those errors conversationally.

#### `DELETE /chat/{chat_id}`

- deletes a chat
- before deletion, records deletion history for every attached form
- relies on relationship cascade to delete forms with the chat

Important interview point:

The chat itself is not tracked in `ChangeHistory`; only form deletions are recorded here.

#### `GET /chat/{chat_id}`

- returns single chat with eager-loaded `form_submissions`

#### `GET /chat/{chat_id}/forms`

- returns forms for a chat
- supports optional `status` filter

#### `GET /form/{form_id}/history`

- returns ordered history for one form

#### `GET /history/{entity_type}/{entity_id}`

- generic history endpoint for any future tracked entity type

#### `PUT /form/{form_id}`

- direct REST form update
- snapshots old values
- applies validated partial update
- records diff history with `change_source="rest_api"`

#### `DELETE /form/{form_id}`

- direct REST deletion
- snapshots old values
- deletes row
- records deletion history

### Interview questions to expect from `main.py`

1. Why does `PUT /chat/{chat_id}` store the whole transcript instead of just the new message?
2. Why is the tool execution on the backend instead of directly in the model?
3. Why are tool responses appended to `messages`?
4. What happens if OpenAI returns malformed tool arguments?
5. Why use `selectinload`?
6. How would you make this more robust for concurrent updates?
7. What if two tool calls update the same form in one request?
8. How would you secure this if there were real users and auth?

## 7.2 `backend/models.py`

Defines SQLAlchemy ORM models.

### Important design choices

- string IDs generated with `secrets.token_urlsafe`
- `Chat.messages` as JSON
- one-to-many `Chat -> FormSubmission`
- cascade delete
- generic `ChangeHistory` table

### Good interview answer

This file is the domain model. It expresses persistence shape, relationships, and what the backend considers a first-class business entity.

## 7.3 `backend/schemas.py`

Defines Pydantic request/response schemas.

### Main schema groups

- `Chat`, `ChatCreate`, `ChatUpdate`
- `FormSubmission`, `FormSubmissionCreate`, `FormSubmissionUpdate`
- `ChangeHistory`, `ChangeHistoryCreate`

### Key point

The ORM model defines storage. The Pydantic schema defines API contract and validation. That separation is a common interview topic.

### Subtle points

- `Chat.form_submissions` is included in the response schema
- `FormSubmissionUpdate` is partial by design
- `Chat.model_rebuild()` resolves the forward reference

## 7.4 `backend/crud.py`

Generic async CRUD layer.

### `CRUDBase`

Provides:

- `get`
- `get_multi`
- `create`
- `update`
- `remove`

### Why it exists

It reduces repeated DB logic across entity types and standardizes behavior.

### Important implementation details

- `create` injects `created_at`
- `update` uses `exclude_unset=True` for partial schema updates
- commit and refresh happen inside CRUD methods

### Tradeoffs

Pros:

- concise and reusable
- easy to add new entities

Cons:

- business logic can leak into generic data-access layer if not disciplined
- per-operation commits make multi-step transactions harder

That second point is a very good interview discussion topic.

## 7.5 `backend/database.py`

Sets up:

- async DB URL
- SQLAlchemy engine
- async sessionmaker
- declarative `Base`

### Current DB choice

SQLite via `sqlite+aiosqlite:///./dev.db`

This is good for local development and take-home simplicity, but not ideal for a heavily concurrent production workload.

## 7.6 `backend/change_tracker.py`

This file implements the audit/history service.

### Internal helpers

- `_next_revision(...)`
- `_serialize_value(...)`
- `_compute_diff(...)`
- `_extract_field_values(...)`

### Public API

- `record_creation(...)`
- `record_update(...)`
- `record_deletion(...)`
- `get_history(...)`

### Why it is well-designed

- history logic is centralized
- endpoints do not hand-build diff JSON
- no-op updates skip history writes
- it works for any entity type with tracked fields

### Potential critique

Each history write is its own DB commit because CRUD methods commit internally. That means update/delete plus history write are not guaranteed to be fully atomic across all steps.

If an interviewer asks for improvement:

- move to a transaction boundary spanning business operation plus history insert
- or redesign CRUD to allow batched commits

## 7.7 `backend/alembic.ini`

Alembic configuration file. It points Alembic at the environment and migration setup.

## 7.8 `backend/alembic/env.py`

This is the Alembic runtime wiring.

### What it does

- loads Alembic config
- imports `Base.metadata`
- sets `target_metadata`
- defines offline and online migration execution
- uses SQLite URL

### Interview question

"Why does Alembic need `target_metadata`?"

Answer:

Because Alembic compares the current ORM model metadata against the database schema when generating or running migrations.

## 7.9 `backend/alembic/versions/546f84e030c3_create_tables.py`

Initial migration.

Creates:

- `chat`
- `form_submission`
- indexes

This is the baseline schema migration.

## 7.10 `backend/alembic/versions/a1b2c3d4e5f6_add_change_history_table.py`

Second migration.

Creates:

- `change_history`
- unique constraint on `(entity_type, entity_id, revision)`
- indexes on key lookup fields

This is the persistence implementation of the Task 3 design.

## 7.11 `backend/tests/conftest.py`

Test infrastructure.

### What it provides

- in-memory SQLite DB
- FastAPI dependency override for `get_db`
- HTTP client via `httpx`
- OpenAI response mocks

This is important because the tests are integration-style API tests without hitting the real OpenAI API.

## 7.12 `backend/tests/test_r1_form_submission.py`

Tests Task 1 behavior.

Key cases:

- happy-path tool call creates form
- partial args trigger validation failure
- malformed JSON does not create form
- multiple tool calls create multiple forms

## 7.13 `backend/tests/test_r2_form_crud.py`

Tests Task 2 behavior.

Key cases:

- update form via REST
- delete form via REST
- status validation
- status filtering
- update via chat tool
- delete via chat tool
- malformed JSON
- missing form ID
- partial update behavior

This is a strong test file for interview discussion because it proves the design is exercised from both API surfaces.

## 7.14 `backend/requirements.txt`

Python dependencies. The exact stack inferred from code includes:

- FastAPI
- SQLAlchemy
- aiosqlite
- Alembic
- OpenAI SDK
- Pydantic
- pytest/httpx for tests

## 7.15 `backend/dev.db`

Local SQLite database file. This is runtime state, not source logic. It should generally not be treated as authoritative design documentation.

## 7.16 `backend/CONTEXT.md`

Short internal explainer summarizing backend architecture, models, CRUD, and task gaps. Useful for ramp-up, but the source of truth is the code.

## 8. Frontend File-by-File Guide

## 8.1 `frontend/app/page.tsx`

Home page listing chats.

### What it does

- fetches chats using SWR
- renders a table with IDs and creation timestamps
- creates new chats
- deletes chats with inline confirmation
- links to each chat detail page

### Current working-tree change

The file has been modified to use `/api/...` proxy routes instead of hardcoded `http://localhost:8000/...`. That is a good deployment improvement because it centralizes backend routing through Next.js rewrites.

## 8.2 `frontend/app/[chatId]/page.tsx`

This is the main UI file and frontend equivalent of `backend/main.py`.

### What it contains

- message rendering
- form list rendering
- inline form editing
- inline form deletion
- status filtering
- change history modal
- chat input and send flow

### Main UI concepts

#### `OpenAIConversationDisplay`

Renders visible chat messages.

Important behavior:

- hides assistant messages that are only tool calls
- hides `role: "tool"` messages from end users

That means the backend stores the full transcript, but the UI intentionally shows a filtered human-friendly view.

#### `FormCard`

Represents one form submission with:

- display mode
- edit mode
- delete confirmation
- history modal toggle

#### `FormSubmissionsPanel`

Displays all current chat forms or an empty-state prompt.

#### `ChangeHistoryPanel`

Loads `GET /form/{form_id}/history` and shows:

- revisions
- event type
- change source
- field-by-field old/new diffs

### State flow

Main page state includes:

- `input`
- `messages`
- `formSubmissions`
- `statusFilter`

### Data flow

- SWR fetches base chat data
- `refreshForms()` fetches forms separately, optionally filtered by status
- chat send triggers `PUT /chat/{chatId}`
- REST form edits trigger `PUT /form/{formId}`
- REST form deletes trigger `DELETE /form/{formId}`
- history modal triggers `GET /form/{formId}/history`

### Interview angles

1. Why keep forms in separate state from chat response?
2. Why filter forms with a separate fetch instead of filtering client-side?
3. Why hide tool messages from the visible transcript?
4. What are the risks of such a large client component?
5. How would you refactor this into smaller components?

## 8.3 `frontend/utils/fetcher.ts`

SWR fetch helper.

### What changed

The current version uses:

```ts
fetch(`/api/${args.url}`)
```

instead of a hardcoded backend origin.

### Why that matters

- avoids hardcoded environment assumptions
- works better with local proxying and deployment setups
- reduces CORS complexity from the browser's perspective

## 8.4 `frontend/next.config.mjs`

Defines rewrite:

```text
/api/:path* -> http://127.0.0.1:8000/:path*
```

This lets frontend code call relative `/api/...` paths while Next proxies to FastAPI.

This is one of the current uncommitted changes in the repo and is worth mentioning in an interview as an infrastructure improvement.

## 8.5 `frontend/app/layout.tsx`

Global layout with font and base body styling.

Low complexity, but interviewers may ask why metadata is still default-generated. Good answer: it is unfinished polish, not core business logic.

## 8.6 `frontend/app/globals.css`

Tailwind imports plus scrollbar styling. Mostly presentation.

Note: the file contains duplicated Tailwind directives. That is harmless but not clean.

## 8.7 `frontend/package.json`

Defines Next.js, React, SWR, Tailwind, TypeScript, ESLint stack.

## 8.8 `frontend/tailwind.config.ts`

Tailwind content paths and basic theme extension.

## 8.9 `frontend/CONTEXT.md`

Short explainer for the original frontend shape before form-management features were added.

## 8.10 Static/generated files

| File | Meaning |
|---|---|
| `frontend/package-lock.json` | npm lockfile |
| `frontend/app/favicon.ico` | icon asset |
| `frontend/public/*.svg` | starter assets |
| `frontend/postcss.config.mjs` | Tailwind/PostCSS wiring |
| `frontend/tsconfig.json` | TS config |

These are low-signal for business logic, but they matter for environment setup and reproducibility.

## 9. Root-Level and Documentation Files

## 9.1 `README.md`

This is the assessment spec. It describes the original tasks and expected stack usage. Read this first in any interview prep because it defines the problem statement.

## 9.2 `task3.md`

Design document for revision history. It explains the chosen JSON-diff-per-revision model, alternatives, and tradeoffs. This is highly interviewable because it shows system design reasoning rather than just code.

## 9.3 `changes/changes-overview.md`

Maps tasks to requirement groups R1/R2/R3 and explains phased implementation.

## 9.4 `changes/R1-requirements.md`

Explains Task 1 implementation expectations:

- persist form submissions
- expose them in API
- show them in UI

## 9.5 `changes/R2-requirements.md`

Explains Task 2 expectations:

- update/delete support
- status validation
- filtered form retrieval
- tool augmentation

## 9.6 `changes/R3-requirements.md`

Breaks down the change history design problem into explicit requirements.

## 9.7 `changes/additional.md`

Documents additional enhancements beyond the strict original tasks, including:

- stronger validation
- delete chat

## 9.8 `create_zip.py`

Packaging helper for submission artifacts.

## 10. What Alembic Is

Alembic is the database migration tool used with SQLAlchemy.

### Simple explanation

Your SQLAlchemy models describe what the schema should look like now.

Alembic is the tool that:

- records schema changes as versioned migration files
- upgrades an existing database from one schema version to another
- can also downgrade if needed

### Why it exists

Without Alembic, changing `models.py` would not change the actual database schema already sitting on disk.

Example:

1. You add a new model or column in `models.py`.
2. The database still has the old schema.
3. Alembic generates or runs a migration to reconcile that difference.

### In this repo specifically

The command in the README:

```bash
alembic upgrade head
```

means:

"Apply all migrations up to the latest revision."

### Files to understand

| File | Role |
|---|---|
| `backend/alembic.ini` | Alembic config |
| `backend/alembic/env.py` | environment bootstrap, DB URL, metadata hookup |
| `backend/alembic/versions/*.py` | versioned migration scripts |

### Migration chain in Aurelian

1. `546f84e030c3_create_tables.py`
   - creates `chat` and `form_submission`
2. `a1b2c3d4e5f6_add_change_history_table.py`
   - creates `change_history`

### Interview-ready explanation

"Alembic is the schema version-control layer for the SQLAlchemy models. It lets the team evolve the database safely and reproducibly across environments instead of relying on ad hoc manual SQL."

## 11. The Main Changes Implemented in This Project

This section is the best answer if the interviewer asks, "What changes did you make?" or "What was added beyond the starting prototype?"

## 11.1 Core functional changes

1. `submit_interest_form` now persists real `FormSubmission` rows instead of returning fake success.
2. chats now expose associated forms in API responses.
3. the chat UI shows forms for the current chat.
4. forms can be updated and deleted through REST endpoints.
5. the AI can also update and delete forms through tool calls.
6. `status` is validated and filterable.
7. change history exists for create, update, and delete operations.
8. a history UI modal displays form revisions.
9. chat deletion now exists and cascades to forms.

## 11.2 Architectural changes

1. introduced a generic `ChangeHistory` model instead of a form-specific history table.
2. centralized history logic in `change_tracker.py`.
3. expanded prompt/tool contract in `SYSTEM_TEMPLATE` and `TOOLS`.
4. added client-side validation that mirrors server rules.
5. improved frontend-backend integration with API proxy rewrites.

## 11.3 Current uncommitted working-tree changes

The repo currently has uncommitted modifications in:

- `frontend/app/page.tsx`
- `frontend/app/[chatId]/page.tsx`
- `frontend/next.config.mjs`
- `frontend/utils/fetcher.ts`
- `frontend/package-lock.json`
- `backend/dev.db`

The meaningful code change among these is the switch from hardcoded backend URLs to relative `/api/...` calls routed through a Next.js rewrite.

That is worth calling out because interviewers often ask about "small but important" improvements.

## 12. Important Tradeoffs and Potential Weaknesses

These are excellent interview talking points because they show judgment.

### 12.1 `Chat.messages` as JSON

Pros:

- simple
- matches OpenAI message format
- fast to prototype

Cons:

- hard to query individual messages
- no message-level indexing
- large chats can create large JSON blobs

### 12.2 Generic CRUD commits on every operation

Pros:

- simple and reusable

Cons:

- multi-step workflows are not fully transactional
- history writes and entity writes can theoretically diverge on partial failure

### 12.3 SQLite for app data

Pros:

- easy local setup

Cons:

- limited concurrency
- not ideal for production-scale write patterns

### 12.4 Large frontend page component

Pros:

- fast to build

Cons:

- mixes rendering, networking, form validation, and modal logic in one file
- harder to test and maintain

### 12.5 Prompt-driven tool use

Pros:

- flexible natural-language UX

Cons:

- model can fail to ask for required info well
- requires strong validation and guardrails

## 13. How I Would Explain the Solution in an Interview

Short version:

"Aurelian is an AI chat app where the assistant can create and manage structured interest forms. The backend exposes a chat endpoint that sends messages and tool definitions to OpenAI. When the model emits a tool call, the backend executes the corresponding business logic, persists `FormSubmission` records, records change history, and then does a second model call so the assistant can reply naturally. The frontend renders the chat and a side panel of forms for that chat, and it also supports direct REST-based editing, deletion, filtering, and history inspection."

## 14. Likely Interview Questions and Strong Answers

### Product / system questions

1. Why is this useful?
   - It turns unstructured AI conversation into structured CRM-like workflow data.

2. Why tie forms to chats?
   - The chat is the interaction context and natural parent container for submissions created during that conversation.

3. Why allow both AI tool updates and REST updates?
   - The AI path enables conversational workflows; the REST path supports deterministic UI operations and easier external integrations.

### Backend questions

1. Why use Pydantic validation if the AI should already provide valid data?
   - AI output is untrusted input. Validation is mandatory.

2. Why add `change_source`?
   - It gives audit context and distinguishes user/UI actions from AI-triggered actions.

3. Why use a polymorphic history table?
   - It makes the audit system reusable for future entities without new schema changes.

4. Why store diffs instead of snapshots?
   - The requirement prioritizes knowing what changed, not reconstructing every full state cheaply.

5. What would you improve first?
   - transactional consistency across update/delete plus history insert, authentication, and refactoring large UI/backend handlers.

### Frontend questions

1. Why use SWR?
   - It simplifies cache-aware GET fetching and refresh behavior.

2. Why separate `refreshForms()` from the base chat fetch?
   - Because forms have independent filtering behavior by status.

3. Why hide tool messages?
   - The DB transcript is for system correctness; the UI transcript is for human readability.

## 15. Interview Notes on Specific Data Types

### `messages: JSON`

Stores arrays of objects shaped roughly like OpenAI chat messages:

- `{ role: "user", content: "..." }`
- `{ role: "assistant", content: "...", tool_calls: [...] }`
- `{ role: "tool", tool_call_id: "...", name: "...", content: "..." }`

### `changes: JSON`

Stores field diffs where each key is a changed field and the value has:

- `old`
- `new`

### `status: Integer | null`

Represents a finite workflow enum encoded as integers.

Why integer instead of string?

- compact storage
- easy filtering
- explicit mapping

Downside:

- less self-documenting than a string enum

## 16. Next Steps Based on What This Project Appears To Be For

This project looks like an early prototype for an AI-assisted intake or lightweight CRM workflow.

The most sensible next steps are:

1. Add authentication and user ownership so chats/forms belong to real users or teams.
2. Replace hardcoded OpenAI and DB environment assumptions with proper config management.
3. Make chat update plus history writes transactional.
4. Normalize messages into a separate table if chat analytics or scaling matter.
5. Add pagination and search for chats and forms.
6. Introduce optimistic UI updates and better loading/error states.
7. Break `frontend/app/[chatId]/page.tsx` into focused components.
8. Add backend authorization checks around form and history endpoints.
9. Move from SQLite to Postgres for stronger concurrency and JSON querying.
10. Add richer workflow state, e.g. assignee, notes, timestamps, and audit actor.
11. Add automated migration generation/checks to CI.
12. Add real monitoring around OpenAI latency, tool failures, and validation errors.

## 17. Best "Deep Dive" Narrative for the Interview

If the interviewer wants a deep technical walkthrough, this is the cleanest structure:

1. Start from `README.md` and explain the original take-home tasks.
2. Explain the three core entities: `Chat`, `FormSubmission`, `ChangeHistory`.
3. Walk the `PUT /chat/{chat_id}` request lifecycle.
4. Explain how Pydantic validation protects against bad AI output.
5. Explain how REST endpoints complement tool-driven workflows.
6. Explain the change-history design and why JSON diff was chosen.
7. Call out tradeoffs: JSON transcript storage, transaction boundaries, and frontend file size.
8. Finish with next-step improvements toward production readiness.

## 18. Final Summary

Aurelian is a compact but high-signal full-stack application. It demonstrates how to combine:

- conversational AI
- deterministic backend business logic
- structured persistence
- REST APIs
- a React/Next UI
- schema migrations
- change auditing

The technical heart of the project is not the chat UI itself. It is the bridge between:

- unstructured natural-language intent
- structured validated data
- traceable business state changes

That is the core idea to keep coming back to in an interview.
