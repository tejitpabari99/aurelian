# Backend Context Summary

## Stack
- **Framework:** FastAPI (async)
- **DB:** SQLite via `aiosqlite` + SQLAlchemy async
- **Migrations:** Alembic
- **AI:** OpenAI SDK (`gpt-4o-mini`)
- **Server:** Uvicorn

## Database (`database.py`)
- SQLite at `./dev.db`, async engine via `create_async_engine`
- `SessionLocal` = async session factory
- `Base` = declarative base for models

## Models (`models.py`)

### Chat
| Column | Type | Notes |
|---|---|---|
| id | String(32) PK | `secrets.token_urlsafe` default |
| created_at | DateTime | indexed |
| messages | JSON | stores full OpenAI message history |
| form_submissions | relationship → FormSubmission | cascade delete |

### FormSubmission
| Column | Type | Notes |
|---|---|---|
| id | String(32) PK | `secrets.token_urlsafe` default |
| created_at | DateTime | indexed |
| chat_id | String(32) FK → chat.id | required |
| name | String | indexed |
| phone_number | String | indexed |
| email | String | indexed |
| status | Integer | indexed, nullable |

## Schemas (`schemas.py`)
- `Chat` / `ChatCreate` / `ChatUpdate` — Chat read has `id, created_at, messages`
- `FormSubmission` / `FormSubmissionCreate` / `FormSubmissionUpdate` — all fields present, already defined but **not yet used anywhere**

## CRUD (`crud.py`)
Generic `CRUDBase` class with: `get`, `get_multi`, `create`, `update`, `remove`

Two instances ready to use:
- **`crud.chat`** — CRUD for Chat
- **`crud.form`** — CRUD for FormSubmission (**exists but unused**)

Key patterns:
- `crud.chat.create(db=db, obj_in=data)` — creates with auto timestamp
- `crud.chat.update(db, db_obj=chat, obj_in=data)` — partial update from dict/schema
- `crud.chat.get(db, id=chat_id)` — get by ID
- `crud.form.create(db=db, obj_in=data)` — ready to use for FormSubmission

## API Endpoints (`main.py`)

| Method | Path | What it does |
|---|---|---|
| GET | `/` | Hello World |
| GET | `/chat` | List chats (limit 10) |
| POST | `/chat` | Create empty chat |
| GET | `/chat/{chat_id}` | Get single chat |
| PUT | `/chat/{chat_id}` | **Main chat endpoint** — sends messages to OpenAI, handles tool calls |

### `PUT /chat/{chat_id}` — Key Logic
1. Gets chat from DB
2. Sends messages to OpenAI with `submit_interest_form` tool definition
3. Appends assistant response to messages
4. **If tool_calls exist:** iterates over them, appends a "Success" tool response for each, then calls OpenAI again to get final assistant reply
5. Updates chat in DB with full message history

### ⚠️ Current Gap (Task 1 Target)
- When `submit_interest_form` tool is called, arguments (name, email, phone_number) are available in `t["function"]["arguments"]` (JSON string) but **nothing is saved to DB**
- Just returns "Success" without creating a `FormSubmission` record
- No endpoint exists to get form submissions for a chat
- `crud.form` exists but is never called
