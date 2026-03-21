# R3 — Change History Design (Task 3)

## Requirement Summary

From the README (Task 3):
> We want to be able to track the full revision history of a Form Submission and all changes made after each update. Design a data model that would allow us to do this. Consider that in the future we may want to track the revision history of other things using this same model. The ability to filter by certain properties is not as important here. We just want to be able to determine **what fields changed**, **what changed about them**, and **when they changed**. No need to write code for this portion. Just include the details of your model and thought process in a file called `task3.md`.

---

## Key Requirements Extracted from Task 3

| # | Requirement | Details |
|---|---|---|
| 1 | **Track full revision history** of a Form Submission | Every update to a FormSubmission must be recorded. The complete history of changes from creation to current state must be reconstructable. |
| 2 | **Track all changes made after each update** | Each update event must capture the individual field-level changes — not just a snapshot of the final state. |
| 3 | **What fields changed** | The model must identify which specific fields were modified in each update (e.g., `name`, `email`, `phone_number`, `status`). |
| 4 | **What changed about them** | The model must capture the old value and the new value for each changed field. |
| 5 | **When they changed** | Each change event must have a timestamp recording when the update occurred. |
| 6 | **Generic / reusable model** | The same data model should be usable for tracking revision history of other entities in the future (e.g., Chat, User, etc.) — not hardcoded to FormSubmission. |
| 7 | **Filtering by properties is NOT a priority** | The model does not need to optimize for querying by specific field values. The focus is on reconstructing history and understanding what changed. |
| 8 | **No code required** | This is a design exercise only. The deliverable is a written document (`task3.md`), not implementation code. |

---

## Current State

### Existing Data Model (Post-R1/R2)

**`FormSubmission` table:**
| Column | Type | Description |
|---|---|---|
| `id` | String(32) | Primary key, auto-generated token |
| `created_at` | DateTime | Creation timestamp |
| `chat_id` | String(32) | Foreign key to `chat.id` |
| `name` | String | User's name |
| `phone_number` | String | User's phone number |
| `email` | String | User's email |
| `status` | Integer | Status: None, 1 (TO DO), 2 (IN PROGRESS), 3 (COMPLETED) |

**What's missing:**
- No revision/history tracking of any kind exists
- When a FormSubmission is updated (via `PUT /form/{form_id}` or `update_form_submission` chat tool), the old values are overwritten with no record of previous state
- No audit trail of who or what triggered the change
- No way to reconstruct previous states of a FormSubmission

### Change Vectors (Where Updates Happen)
Updates to FormSubmission can come from two sources (established in R2):
1. **REST API:** `PUT /form/{form_id}` — direct HTTP update
2. **Chat bot tool:** `update_form_submission` tool call within `PUT /chat/{chat_id}`

Both sources should be tracked by the change history model.

---

## Deliverable

A single file: **`task3.md`** in the project root.

### Required Content for `task3.md`

The document must include:

#### 1. Data Model Design
- Table/entity definition(s) for tracking change history
- Column definitions with types and descriptions
- Relationships to existing tables (if any)
- Primary key strategy
- Indexing considerations (keeping in mind that filtering is not a priority, but timestamp-based lookups likely are)

#### 2. How the Model Satisfies Each Requirement

| Requirement | How the model addresses it |
|---|---|
| Track full revision history | How are revisions linked to the source entity? |
| Track all changes per update | How are individual field changes captured within a single update event? |
| What fields changed | How is the field name stored/identified? |
| What changed (old → new values) | How are old and new values stored? How are different data types handled (string, integer, null)? |
| When they changed | Where is the timestamp? What timezone/format? |
| Generic / reusable | How does the model accommodate different entity types without schema changes? |

#### 3. Design Alternatives Considered
- At least 2-3 alternative approaches should be discussed
- Pros and cons of each
- Justification for the chosen approach

#### 4. Thought Process
- Reasoning behind key design decisions
- Trade-offs acknowledged
- Future considerations

---

## Design Considerations to Address

The following are important design questions that the `task3.md` document should address:

### A. Granularity: Field-Level vs. Snapshot vs. Diff

| Approach | Description | Pros | Cons |
|---|---|---|---|
| **Field-level changes** | One row per changed field per update event (e.g., `entity_type="form_submission", entity_id="abc", field_name="name", old_value="John", new_value="Jane"`) | Easy to query individual field history; clear and explicit | More rows per update; old/new values stored as strings (lose type info) |
| **Snapshot** | Store the full entity state as JSON at each revision (e.g., `snapshot={"name":"Jane","email":"jane@test.com",...}`) | Simple to reconstruct state at any point; preserves types in JSON | Harder to see what specifically changed; storage grows with entity size; diffing required to determine changes |
| **JSON diff** | Store a JSON object of changes per revision (e.g., `changes={"name":{"old":"John","new":"Jane"}}`) | Compact; groups all changes in one update; easy to see what changed | Harder to query individual field history; JSON querying varies by DB |

### B. Generic Entity Reference
Since the model must be reusable for entities beyond FormSubmission:
- How to reference the source entity? Options: `entity_type` + `entity_id` (polymorphic), vs. separate history tables per entity type
- Trade-offs: polymorphic is flexible but loses FK constraints; per-entity tables are type-safe but require schema changes for each new entity

### C. Change Context / Metadata
Consider whether to capture:
- **Who** made the change (user ID, system, chat bot) — not explicitly required by Task 3, but valuable for audit
- **How** the change was triggered (REST API vs. chat tool) — the change source/vector
- **Why** / change reason — optional metadata

### D. Data Type Handling
When storing old/new values:
- Different fields have different types (String for name/email/phone, Integer for status, etc.)
- If storing as strings: need serialization/deserialization strategy
- If storing as JSON: native type preservation but DB-specific querying

### E. Null Handling
- `status` field can be `None` → need to distinguish "field was null" from "field was not changed"
- Important for the diff/field-level approaches

### F. Creation Event
- Should the initial creation of a FormSubmission also be recorded as a revision? (All fields "changed" from null to their initial values)
- Or does history tracking only start after the first update?

### G. Deletion Event
- Should deletion of a FormSubmission be recorded in the history?
- If so, how? (A final revision entry with `event_type="deleted"`)

### H. Ordering and Sequencing
- How to order revisions? Options: timestamp only, or revision number + timestamp
- Revision numbers provide deterministic ordering even if timestamps collide

---

## Example Model Sketch (for reference — the candidate should design their own)

This is provided as a reference point, NOT as the prescribed solution. The candidate should propose and justify their own design.

### Option A: Field-Level Change Log

```
Table: change_history
├── id              (String PK)       — unique change record ID
├── created_at      (DateTime)        — when the change occurred
├── entity_type     (String)          — e.g., "form_submission", "chat"
├── entity_id       (String)          — ID of the entity that changed
├── revision        (Integer)         — sequential revision number per entity
├── field_name      (String)          — which field changed (e.g., "name", "status")
├── old_value       (String, nullable)— previous value (serialized to string)
├── new_value       (String, nullable)— new value (serialized to string)
└── change_source   (String, nullable)— optional: "rest_api", "chat_tool", etc.
```

### Option B: Revision Snapshot

```
Table: entity_revision
├── id              (String PK)       — unique revision ID
├── created_at      (DateTime)        — when the revision was created
├── entity_type     (String)          — e.g., "form_submission"
├── entity_id       (String)          — ID of the entity
├── revision        (Integer)         — sequential revision number
├── snapshot        (JSON)            — full entity state at this revision
└── change_source   (String, nullable)— optional context
```

### Option C: JSON Diff Per Revision

```
Table: change_record
├── id              (String PK)       — unique record ID
├── created_at      (DateTime)        — when the change occurred
├── entity_type     (String)          — e.g., "form_submission"
├── entity_id       (String)          — ID of the entity
├── revision        (Integer)         — sequential revision number
├── changes         (JSON)            — {"field": {"old": ..., "new": ...}, ...}
└── change_source   (String, nullable)— optional context
```

---

## What the Document Should NOT Include

- Implementation code (models.py, migrations, CRUD operations, API endpoints)
- Frontend changes
- Test code

Task 3 is explicitly a **design-only** exercise: _"No need to write code for this portion."_

---

## Evaluation Criteria

The `task3.md` document will be evaluated on:

| Criteria | What to look for |
|---|---|
| **Completeness** | Does the model address all 6 core requirements (history, changes, what/what changed/when, generic)? |
| **Clarity** | Is the model clearly described? Are column types and purposes well-documented? |
| **Genericity** | Can the model track history for entities other than FormSubmission without schema changes? |
| **Trade-off awareness** | Are alternative approaches discussed? Are pros/cons acknowledged? |
| **Practicality** | Is the design realistic to implement? Does it consider real-world concerns (data types, nulls, ordering)? |
| **Thought process** | Is the reasoning behind decisions clearly explained? |

---

## Relationship to Other Requirements

| Requirement | Relationship |
|---|---|
| **R1** (Save FormSubmission) | R3's change history model would track the creation event if the design includes initial creation tracking |
| **R2** (Update/Delete via chat + REST API) | R3's change history model would track all updates and deletions made through both the REST API and chat bot tools. The update/delete operations from R2 are the primary change vectors that generate history entries. |
| **R3** (This requirement) | Design-only. No code. Produces `task3.md`. |

---

## Definition of Done

- [ ] `task3.md` file created in the project root
- [ ] Data model design clearly defined with table structure, column types, and descriptions
- [ ] Model addresses: what fields changed, what the old/new values are, and when the change occurred
- [ ] Model is generic — can track revision history for entities beyond FormSubmission
- [ ] At least 2-3 design alternatives discussed with pros/cons
- [ ] Thought process and reasoning behind the chosen approach clearly explained
- [ ] Creation and deletion events addressed (whether tracked or not, with justification)
- [ ] Data type handling strategy explained (how different field types are stored in history)
- [ ] No implementation code included (design document only)
