from typing import Optional
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


# Resolve forward reference for Chat.form_submissions -> FormSubmission
Chat.model_rebuild()
