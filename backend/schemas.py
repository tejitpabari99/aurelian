from typing import Optional
import uuid
from datetime import datetime

from pydantic import BaseModel


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

class FormSubmissionUpdate(BaseModel):
    name: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    status: Optional[int] = None


# Resolve forward reference for Chat.form_submissions -> FormSubmission
Chat.model_rebuild()
