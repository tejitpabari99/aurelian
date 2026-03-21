from typing import Optional
import re
import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


class Chat(BaseModel):
    id: str
    created_at: datetime
    messages: list
    form_submissions: list["FormSubmission"] = []

    class Config:
        orm_mode=True

class ChatCreate(BaseModel):
    messages: list = []

class ChatUpdate(BaseModel):
    messages: list


class FormSubmission(BaseModel):
    id: str
    created_at: datetime
    name: str
    phone_number: str
    email: str
    status: Optional[int] = None

    class Config:
        orm_mode=True

# ---------------------------------------------------------------------------
# Shared validation helpers
# ---------------------------------------------------------------------------
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
_PHONE_RE = re.compile(r"^\+?[\d\s\-().]{7,20}$")
# Block obvious HTML / script injection attempts
_SCRIPT_RE = re.compile(r"<\s*script|javascript\s*:|on\w+\s*=", re.IGNORECASE)


def _validate_email(v: str) -> str:
    v = v.strip()
    if not _EMAIL_RE.match(v):
        raise ValueError(
            "Invalid email format. Please provide a valid email address (e.g. user@example.com)"
        )
    return v


def _validate_phone(v: str) -> str:
    v = v.strip()
    if not _PHONE_RE.match(v):
        raise ValueError(
            "Invalid phone number format. Please provide a valid phone number "
            "(digits, spaces, dashes, parentheses allowed, 7-20 characters)"
        )
    return v


def _validate_name(v: str) -> str:
    v = v.strip()
    if len(v) < 1:
        raise ValueError("Name must not be empty")
    if len(v) > 200:
        raise ValueError("Name must be 200 characters or fewer")
    if _SCRIPT_RE.search(v):
        raise ValueError("Name contains disallowed content")
    return v


def _sanitize_text(v: str) -> str:
    """Generic text sanitization: strip and reject script-like content."""
    v = v.strip()
    if _SCRIPT_RE.search(v):
        raise ValueError("Input contains disallowed content")
    return v


class FormSubmissionCreate(BaseModel):
    name: str
    phone_number: str
    email: str
    chat_id: str
    status: Optional[int] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        return _validate_name(v)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        return _validate_email(v)

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, v):
        return _validate_phone(v)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v is not None and v not in (1, 2, 3):
            raise ValueError("status must be None, 1 (TO DO), 2 (IN PROGRESS), or 3 (COMPLETED)")
        return v

class FormSubmissionUpdate(BaseModel):
    name: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    status: Optional[int] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if v is not None:
            return _validate_name(v)
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        if v is not None:
            return _validate_email(v)
        return v

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, v):
        if v is not None:
            return _validate_phone(v)
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v is not None and v not in (1, 2, 3):
            raise ValueError("status must be None, 1 (TO DO), 2 (IN PROGRESS), or 3 (COMPLETED)")
        return v


class ChangeHistory(BaseModel):
    """Read schema for a single change history entry."""
    id: str
    created_at: datetime
    entity_type: str
    entity_id: str
    revision: int
    event_type: str          # "created" | "updated" | "deleted"
    changes: Optional[dict] = None
    change_source: Optional[str] = None

    class Config:
        orm_mode = True


class ChangeHistoryCreate(BaseModel):
    """Internal-use schema for inserting a change history row."""
    entity_type: str
    entity_id: str
    revision: int
    event_type: str
    changes: Optional[dict] = None
    change_source: Optional[str] = None


# Resolve forward reference for Chat.form_submissions -> FormSubmission
Chat.model_rebuild()
