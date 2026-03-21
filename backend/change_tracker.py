"""
Change history tracking service.

Provides helper functions to record create / update / delete events for any
entity into the generic ``change_history`` table.  The diff computation
follows the JSON-diff-per-revision approach described in task3.md.
"""

import logging
from typing import Any, Dict, List, Optional, Sequence

from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import crud
import schemas
from models import ChangeHistory

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _next_revision(
    db: AsyncSession,
    entity_type: str,
    entity_id: str,
) -> int:
    """Return the next revision number for a given (entity_type, entity_id).

    If no history exists yet the first revision is 1.
    """
    stmt = (
        select(func.max(ChangeHistory.revision))
        .where(ChangeHistory.entity_type == entity_type)
        .where(ChangeHistory.entity_id == entity_id)
    )
    result = await db.scalar(stmt)
    return (result or 0) + 1


def _serialize_value(value: Any) -> Any:
    """Ensure a value is JSON-serialisable.

    Primitive types (str, int, float, bool, None) pass through unchanged.
    Everything else is converted via ``jsonable_encoder`` so that datetimes,
    enums, etc. are handled gracefully.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return jsonable_encoder(value)


def _compute_diff(
    old_values: Dict[str, Any],
    new_values: Dict[str, Any],
    tracked_fields: Sequence[str],
) -> Dict[str, Dict[str, Any]]:
    """Compute a field-level diff between *old_values* and *new_values*.

    Only fields listed in *tracked_fields* are considered.  Fields whose
    value did not actually change are **excluded** from the result.

    Returns a dict like::

        {"name": {"old": "John", "new": "Jane"}, "status": {"old": null, "new": 2}}

    An empty dict means nothing changed.
    """
    diff: Dict[str, Dict[str, Any]] = {}
    for field in tracked_fields:
        old = _serialize_value(old_values.get(field))
        new = _serialize_value(new_values.get(field))
        if old != new:
            diff[field] = {"old": old, "new": new}
    return diff


def _extract_field_values(
    db_obj: Any,
    tracked_fields: Sequence[str],
) -> Dict[str, Any]:
    """Read current column values from a SQLAlchemy model instance."""
    return {field: getattr(db_obj, field, None) for field in tracked_fields}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def record_creation(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: str,
    field_values: Dict[str, Any],
    tracked_fields: Sequence[str],
    change_source: Optional[str] = None,
) -> ChangeHistory:
    """Record a 'created' event for a newly created entity.

    All tracked fields are recorded with ``old: null`` → ``new: <value>``.
    """
    changes = {
        field: {"old": None, "new": _serialize_value(field_values.get(field))}
        for field in tracked_fields
    }

    revision = await _next_revision(db, entity_type, entity_id)

    entry = schemas.ChangeHistoryCreate(
        entity_type=entity_type,
        entity_id=entity_id,
        revision=revision,
        event_type="created",
        changes=changes,
        change_source=change_source,
    )

    row = await crud.change_history.create(db=db, obj_in=entry)
    logger.info(
        "ChangeHistory recorded: event=%s entity=%s/%s rev=%d source=%s",
        "created", entity_type, entity_id, revision, change_source,
    )
    return row


async def record_update(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: str,
    old_values: Dict[str, Any],
    new_values: Dict[str, Any],
    tracked_fields: Sequence[str],
    change_source: Optional[str] = None,
) -> Optional[ChangeHistory]:
    """Record an 'updated' event, but **only** if at least one field actually changed.

    Returns the created ``ChangeHistory`` row, or ``None`` if no fields
    actually differed (i.e. a no-op update).
    """
    diff = _compute_diff(old_values, new_values, tracked_fields)

    if not diff:
        logger.debug(
            "ChangeHistory skipped (no-op update): entity=%s/%s",
            entity_type, entity_id,
        )
        return None

    revision = await _next_revision(db, entity_type, entity_id)

    entry = schemas.ChangeHistoryCreate(
        entity_type=entity_type,
        entity_id=entity_id,
        revision=revision,
        event_type="updated",
        changes=diff,
        change_source=change_source,
    )

    row = await crud.change_history.create(db=db, obj_in=entry)
    logger.info(
        "ChangeHistory recorded: event=%s entity=%s/%s rev=%d fields=%s source=%s",
        "updated", entity_type, entity_id, revision, list(diff.keys()), change_source,
    )
    return row


async def record_deletion(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: str,
    field_values: Dict[str, Any],
    tracked_fields: Sequence[str],
    change_source: Optional[str] = None,
) -> ChangeHistory:
    """Record a 'deleted' event.  All tracked fields go ``old: <value>`` → ``new: null``."""
    changes = {
        field: {"old": _serialize_value(field_values.get(field)), "new": None}
        for field in tracked_fields
    }

    revision = await _next_revision(db, entity_type, entity_id)

    entry = schemas.ChangeHistoryCreate(
        entity_type=entity_type,
        entity_id=entity_id,
        revision=revision,
        event_type="deleted",
        changes=changes,
        change_source=change_source,
    )

    row = await crud.change_history.create(db=db, obj_in=entry)
    logger.info(
        "ChangeHistory recorded: event=%s entity=%s/%s rev=%d source=%s",
        "deleted", entity_type, entity_id, revision, change_source,
    )
    return row


async def get_history(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: str,
) -> List[ChangeHistory]:
    """Retrieve the full ordered change history for a specific entity."""
    rows = await crud.change_history.get_multi(
        db,
        filters=[
            ChangeHistory.entity_type == entity_type,
            ChangeHistory.entity_id == entity_id,
        ],
        limit=10000,  # practical upper bound; history shouldn't be paginated normally
    )
    # Sort by revision to guarantee deterministic order
    return sorted(rows, key=lambda r: r.revision)
