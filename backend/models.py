import uuid

from sqlalchemy import JSON, UUID, Column, DateTime, ForeignKey, String, Integer, UniqueConstraint
from sqlalchemy.orm import relationship
import secrets

from database import Base


class Chat(Base):
    __tablename__ = "chat"

    id = Column(String(length=32), primary_key=True, index=True, default=secrets.token_urlsafe)
    created_at = Column(DateTime, index=True)
    messages = Column(JSON)
    form_submissions = relationship(
        "FormSubmission", cascade="all, delete", back_populates="chat"
    )

class FormSubmission(Base):
    __tablename__ = "form_submission"

    id = Column(String(length=32), primary_key=True, index=True, default=secrets.token_urlsafe)
    created_at = Column(DateTime, index=True)
    chat_id = Column(
        String(length=32), ForeignKey("chat.id"), index=True, nullable=False
    )
    chat = relationship("Chat", back_populates="form_submissions")
    name = Column(String, index=True)
    phone_number = Column(String, index=True)
    email = Column(String, index=True)
    status = Column(Integer, index=True)

    # Fields tracked by change history (used by change_tracker to compute diffs)
    TRACKED_FIELDS = ("name", "phone_number", "email", "status")


class ChangeHistory(Base):
    """Generic change history table – one row per create/update/delete event.

    Uses a polymorphic (entity_type + entity_id) reference so the same table
    can track revision history for *any* entity without schema changes.
    See task3.md for the full design rationale.
    """

    __tablename__ = "change_history"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "revision", name="uq_entity_revision"),
    )

    id = Column(String(length=32), primary_key=True, index=True, default=secrets.token_urlsafe)
    created_at = Column(DateTime, index=True, nullable=False)
    entity_type = Column(String(length=64), nullable=False, index=True)
    entity_id = Column(String(length=32), nullable=False, index=True)
    revision = Column(Integer, nullable=False)
    event_type = Column(String(length=16), nullable=False)   # "created", "updated", "deleted"
    changes = Column(JSON, nullable=True)                     # {"field": {"old": ..., "new": ...}, ...}
    change_source = Column(String(length=32), nullable=True)  # "rest_api", "chat_tool", etc.
    
