# Task 3 — Change History Data Model Design

## Overview

This document proposes a data model for tracking the full revision history of Form Submissions (and any future entity) across the application. The goal is to answer three questions for every change: **what fields changed**, **what the old and new values were**, and **when the change happened** — all through a generic, reusable design that requires no schema changes when new entity types are added.

---

## Chosen Approach: JSON Diff Per Revision

After evaluating several alternatives (discussed below), I chose a **JSON diff per revision** model — one row per update event, with a JSON column capturing all field-level changes (`old_value` → `new_value`) for that event.

### Table: `change_history`

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | `String(32)` PK | No | Unique identifier for this history entry (auto-generated token, same strategy as existing tables). |
| `created_at` | `DateTime` | No | UTC timestamp of when the change occurred. |
| `entity_type` | `String(64)` | No | The type of entity that changed, e.g. `"form_submission"`, `"chat"`. Enables reuse across any entity. |
| `entity_id` | `String(32)` | No | The primary key of the entity instance that changed (e.g. the `FormSubmission.id`). |
| `revision` | `Integer` | No | Monotonically increasing revision number per `(entity_type, entity_id)` pair. Starts at 1. |
| `event_type` | `String(16)` | No | One of `"created"`, `"updated"`, `"deleted"`. Distinguishes the nature of the change. |
| `changes` | `JSON` | Yes | A JSON object describing field-level changes. Structure: `{"field_name": {"old": <value>, "new": <value>}, ...}`. Null for `"deleted"` events if no field diff is meaningful. |
| `change_source` | `String(32)` | Yes | How the change was triggered: `"rest_api"`, `"chat_tool"`, or other future sources. Useful for audit context. |

#### Indexes

| Index | Columns | Rationale |
|---|---|---|
| Primary key | `id` | Unique row lookup. |
| Composite | `(entity_type, entity_id, revision)` | Unique constraint. Fast retrieval of the full ordered history for any entity. |
| Timestamp | `created_at` | Supports time-range queries ("what changed in the last hour?"). |

> **Note on filtering:** The requirements explicitly state that filtering by specific property values is not a priority. Therefore, no indexes on the JSON `changes` content are proposed. The indexes above focus on entity lookup and chronological ordering.

#### Relationships

The `change_history` table uses a **polymorphic reference** (`entity_type` + `entity_id`) rather than a direct foreign key. This means:

- No FK constraint to `form_submission.id` or any other table.
- The trade-off is intentional: we gain full genericity (any future entity can be tracked without schema changes) at the cost of losing referential integrity enforcement at the database level. Application-level logic is responsible for writing valid `entity_type`/`entity_id` pairs.
- If an entity is hard-deleted, its history rows remain as an audit trail (orphaned by design, not by accident).

---

## How the Model Satisfies Each Requirement

| Requirement | How the model addresses it |
|---|---|
| **Track full revision history** | Every create, update, and delete event produces a row in `change_history` linked by `(entity_type, entity_id)`. Querying `WHERE entity_type = 'form_submission' AND entity_id = :id ORDER BY revision` reconstructs the complete timeline. |
| **Track all changes per update** | The `changes` JSON column captures every field that was modified in a single update event as one atomic row. A single `PUT /form/{form_id}` that changes both `name` and `status` produces one row with both field diffs. |
| **What fields changed** | The top-level keys in the `changes` JSON object are the field names (e.g. `"name"`, `"status"`, `"email"`). |
| **What changed (old → new)** | Each key maps to `{"old": <previous_value>, "new": <updated_value>}`, making the before/after explicit. |
| **When they changed** | The `created_at` column stores the UTC timestamp of the event. The `revision` column provides deterministic ordering even if two changes share the same second-level timestamp. |
| **Generic / reusable** | `entity_type` is a plain string — tracking history for a `Chat`, `User`, or any future model requires zero schema changes. Just write rows with the appropriate `entity_type`. |

---

## Design Alternatives Considered

### Alternative A: Field-Level Change Log (One Row Per Field Per Event)

```
Table: field_change_log
├── id              String PK
├── created_at      DateTime
├── entity_type     String
├── entity_id       String
├── revision        Integer
├── field_name      String        ← e.g. "name", "status"
├── old_value       String (nullable)
├── new_value       String (nullable)
└── change_source   String (nullable)
```

**Pros:**
- Very easy to query the history of a single field across time (`WHERE field_name = 'status'`).
- Each row is self-contained and simple.
- Relational purists prefer it — no JSON involved.

**Cons:**
- A single update touching 3 fields produces 3 rows, leading to significantly more rows at scale.
- `old_value` / `new_value` must be serialized to strings for all types (integers, nulls, etc.), losing native type information. Requires a serialization/deserialization convention.
- Grouping changes "per update event" requires joining on `(entity_id, revision)`, adding query complexity.
- Distinguishing `null` (the field was null) from missing (the field was not changed) requires careful handling since the row simply wouldn't exist for unchanged fields, but the `old_value` column itself can be `NULL`.

**Why I didn't choose it:** The requirements emphasize understanding *what changed per update*, not querying individual field histories. The field-level approach optimizes for the wrong access pattern and generates more rows. Since filtering by specific properties is explicitly deprioritized, the querying advantage of this approach is not needed.

### Alternative B: Full Snapshot Per Revision

```
Table: entity_snapshot
├── id              String PK
├── created_at      DateTime
├── entity_type     String
├── entity_id       String
├── revision        Integer
├── snapshot        JSON           ← full entity state at this point in time
└── change_source   String (nullable)
```

**Pros:**
- Trivially reconstructs the exact state of an entity at any point in time — just read the `snapshot`.
- No diffing logic needed at write time.
- Preserves native types within JSON.

**Cons:**
- Does **not** directly answer "what fields changed" — you must diff consecutive snapshots to determine changes, pushing complexity to read time.
- Storage grows linearly with entity size × number of revisions, even if only one field changed.
- For a `FormSubmission` with 4-5 fields this is tolerable, but for larger entities with JSON blobs (like `Chat.messages`) it would be expensive.

**Why I didn't choose it:** The core requirement is to know *what changed and how*, not to reconstruct full state. Snapshots defer the "what changed" computation to query time, which directly contradicts the design intent. Additionally, storage inefficiency would compound if this model is reused for entities with large payloads.

### Alternative C (Chosen): JSON Diff Per Revision

This is the approach described in the main proposal above.

**Pros:**
- Directly answers "what changed" without any diffing at read time.
- One row per update event keeps the table compact.
- JSON preserves native types (strings stay strings, integers stay integers, nulls stay nulls).
- Easy to extend — adding a new field to `FormSubmission` in the future requires no changes to `change_history`.
- Grouping changes per event is natural (they're already in one row).

**Cons:**
- Querying the history of a single specific field requires JSON path extraction, which varies by database engine (SQLite `json_extract`, PostgreSQL `->>`). However, the requirements explicitly say filtering by properties is not a priority.
- Slightly more logic at write time to compute the diff before persisting.

**Why I chose it:** It directly and efficiently addresses every stated requirement — what changed, what the old/new values were, when, and generically across entities — with a single compact row per event. The trade-offs (JSON querying complexity) align well with the stated non-priorities (filtering by specific properties).

---

## Thought Process and Design Decisions

### 1. Polymorphic Entity Reference vs. Per-Entity History Tables

I considered creating separate history tables per entity type (e.g. `form_submission_history`, `chat_history`). This would allow proper foreign key constraints and type-safe schemas. However, the requirement explicitly asks for a model that can "track the revision history of other things using this same model." A polymorphic `(entity_type, entity_id)` pair satisfies this directly — adding a new entity requires zero schema migrations.

The FK constraint loss is an acceptable trade-off for a write-heavy audit log where data integrity is enforced at the application layer.

### 2. Recording Creation Events

I recommend recording the initial creation of an entity as a `"created"` event with `revision = 1`. The `changes` JSON would contain all initial field values with `"old": null`:

```json
{
  "name": {"old": null, "new": "John Doe"},
  "email": {"old": null, "new": "john@example.com"},
  "phone_number": {"old": null, "new": "555-0100"},
  "status": {"old": null, "new": null}
}
```

**Rationale:** This establishes a complete baseline. Without it, the history only starts from the first *update*, and the original state is lost if the entity is later modified. Recording creation also means `revision = 1` always represents the birth of the entity, providing a clean chronological narrative.

### 3. Recording Deletion Events

Deletions should be recorded as a `"deleted"` event. The `changes` JSON captures the final state transitioning to null:

```json
{
  "name": {"old": "Jane Doe", "new": null},
  "email": {"old": "jane@example.com", "new": null},
  "phone_number": {"old": "555-0100", "new": null},
  "status": {"old": 2, "new": null}
}
```

**Rationale:** Without this, a deleted entity's history would end abruptly with no indication of deletion. Recording it preserves a complete audit trail, which is especially valuable when the history rows intentionally outlive the entity itself.

### 4. Handling Data Types in JSON

The `changes` column uses the database's native JSON type, which preserves:
- Strings: `"old": "John"` → `"new": "Jane"`
- Integers: `"old": 1` → `"new": 3`
- Nulls: `"old": null` → `"new": 2`

This avoids the string-serialization problem of the field-level approach. JSON natively supports all the types currently used in `FormSubmission` (strings and integers), and would also handle booleans, arrays, and nested objects if future entities need them.

### 5. Null Handling

The JSON diff approach cleanly handles nulls:
- **Field was null, now has a value:** `{"status": {"old": null, "new": 1}}`
- **Field had a value, now null:** `{"status": {"old": 2, "new": null}}`
- **Field was not changed:** The field is simply absent from the `changes` object.

The distinction between "null" and "not present" is inherent to JSON object structure, so no special encoding is needed.

### 6. Ordering: Revision Number + Timestamp

I include both a `revision` integer and a `created_at` timestamp:
- `revision` provides **deterministic ordering** — even if two updates happen within the same millisecond (unlikely but possible in automated/batch scenarios), their order is unambiguous.
- `created_at` provides **human-readable context** and supports time-range queries.
- The unique constraint on `(entity_type, entity_id, revision)` prevents duplicate revision numbers.

### 7. Change Source Tracking

Although not explicitly required by Task 3, I included an optional `change_source` column. The system already has two distinct update vectors (REST API at `PUT /form/{form_id}` and chat bot tool calls within `PUT /chat/{chat_id}`), and knowing *how* a change was triggered is valuable audit context that costs almost nothing to capture.

### 8. What This Model Does NOT Include (and Why)

- **Who made the change (user ID):** The current system has no user/authentication model. If one is added later, a `changed_by` column could be added to `change_history`.
- **Change reason / comment:** Not required by Task 3. Could be added as an optional `note` text column in the future.
- **Optimized property filtering:** Explicitly deprioritized by the requirements. No GIN indexes on JSON or materialized columns.

---

## Example Usage

### After creating a FormSubmission (via chat tool or API):

```
change_history row:
  id:            "abc123"
  created_at:    2026-03-20T19:00:00Z
  entity_type:   "form_submission"
  entity_id:     "xyz789"
  revision:      1
  event_type:    "created"
  changes:       {"name": {"old": null, "new": "John Doe"},
                  "email": {"old": null, "new": "john@test.com"},
                  "phone_number": {"old": null, "new": "555-0100"},
                  "status": {"old": null, "new": null}}
  change_source: "chat_tool"
```

### After updating name and status via REST API:

```
change_history row:
  id:            "def456"
  created_at:    2026-03-20T19:05:00Z
  entity_type:   "form_submission"
  entity_id:     "xyz789"
  revision:      2
  event_type:    "updated"
  changes:       {"name": {"old": "John Doe", "new": "Jane Doe"},
                  "status": {"old": null, "new": 2}}
  change_source: "rest_api"
```

### After deleting the FormSubmission:

```
change_history row:
  id:            "ghi789"
  created_at:    2026-03-20T19:10:00Z
  entity_type:   "form_submission"
  entity_id:     "xyz789"
  revision:      3
  event_type:    "deleted"
  changes:       {"name": {"old": "Jane Doe", "new": null},
                  "email": {"old": "john@test.com", "new": null},
                  "phone_number": {"old": "555-0100", "new": null},
                  "status": {"old": 2, "new": null}}
  change_source: "rest_api"
```

### Reconstructing full history:

```sql
SELECT * FROM change_history
WHERE entity_type = 'form_submission' AND entity_id = 'xyz789'
ORDER BY revision;
```

Returns 3 rows showing the complete lifecycle: creation → update → deletion.

---

## Future Extensibility

- **New entity types:** Just write `change_history` rows with `entity_type = "chat"` (or whatever the new entity is). No migrations needed.
- **User attribution:** Add an optional `changed_by` column when an auth system exists.
- **Batch operations:** The `revision` number and `change_source` columns support tracing bulk updates.
- **Undo/rollback:** Because old values are preserved in every diff, programmatic rollback of any revision is straightforward — apply `old` values from the `changes` JSON in reverse revision order.
