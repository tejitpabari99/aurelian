# Additional Changes

## 1. Input Validation (Backend + Frontend)

**Backend (`schemas.py`):** Added Pydantic `field_validator`s on `FormSubmissionCreate` and `FormSubmissionUpdate`:
- **Email** — must match `user@domain.tld` pattern.
- **Phone** — 7-20 characters; digits, spaces, dashes, parentheses allowed.
- **Name** — non-empty, ≤200 chars, no `<script>` / `javascript:` / `onclick=` injection.

**Backend (`main.py`):** Added `except ValidationError` handlers in the `submit_interest_form` and `update_form_submission` chat tool call flows so validation errors are surfaced as descriptive messages to the LLM (and ultimately the user) instead of generic failures.

**Frontend (`[chatId]/page.tsx`):** Added matching client-side validation in the form edit card. Invalid fields show inline red error text and red borders; errors clear on typing.

### Files changed
- `backend/schemas.py`
- `backend/main.py`
- `frontend/app/[chatId]/page.tsx`
- `backend/tests/test_r1_form_submission.py` (updated partial-args test to expect validation error)
- `backend/tests/test_r2_form_crud.py` (fixed test data to use valid phone numbers)

---

## 2. Delete Chat

**Backend (`main.py`):** Added `DELETE /chat/{chat_id}` endpoint. Deletes the chat and cascades to its form submissions, recording change history for each deleted form.

**Frontend (`page.tsx`):** Added a "Delete" button per row in the chat list table with inline Yes/No confirmation. On confirm, calls the delete endpoint and refreshes the list.

### Files changed
- `backend/main.py`
- `frontend/app/page.tsx`
