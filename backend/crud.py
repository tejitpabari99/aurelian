import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar, Union

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Base, Chat, FormSubmission, ChangeHistory
import schemas

logger = logging.getLogger(__name__)

ModelType = TypeVar("ModelType", bound=Base)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)


class CRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, model: Type[ModelType]):
        """
                CRUD object with default methods to Create, Read, Update, Delete (CRUD).

                **Parameters**

            UserAccessPolicy,
        UserAccessPolicy,
        """
        self.model = model

    async def get(
        self, db: AsyncSession, id: Union[uuid.UUID, str, int], options: list = []
    ) -> Optional[ModelType]:
        logger.debug("DB get %s id=%s", self.model.__tablename__, id)
        statement = select(self.model).filter(self.model.id == id).options(*options)
        result = await db.scalars(statement)
        obj = result.first()
        if obj is None:
            logger.debug("DB get %s id=%s — not found", self.model.__tablename__, id)
        return obj

    async def get_multi(
        self, db: AsyncSession, *, filters: list = [], skip: int = 0, limit: int = 100, options: list = []
    ) -> List[ModelType]:
        logger.debug("DB get_multi %s (skip=%d, limit=%d)", self.model.__tablename__, skip, limit)
        statement = select(self.model).filter(*filters).options(*options).offset(skip).limit(limit)
        result = await db.scalars(statement)
        rows = result.all()
        logger.debug("DB get_multi %s — returned %d rows", self.model.__tablename__, len(rows))
        return rows

    async def create(self, db: AsyncSession, *, obj_in: CreateSchemaType) -> ModelType:
        obj_in_data = jsonable_encoder(obj_in)
        db_obj = self.model(
            **obj_in_data, created_at=datetime.now(timezone.utc).replace(tzinfo=None)
        )  # type: ignore

        db.add(db_obj)

        t0 = time.perf_counter()
        await db.commit()
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.debug("DB create %s — commit took %.1f ms", self.model.__tablename__, elapsed_ms)

        await db.refresh(db_obj)
        logger.debug("DB create %s — id=%s", self.model.__tablename__, db_obj.id)
        return db_obj

    async def update(
        self,
        db: AsyncSession,
        *,
        db_obj: ModelType,
        obj_in: Union[UpdateSchemaType, Dict[str, Any]],
    ) -> ModelType:
        obj_data = jsonable_encoder(
            db_obj, exclude={"embedding", "vector", "routing_options"}
        )
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = jsonable_encoder(obj_in, exclude_unset=True)
        for field in obj_data:
            if field in update_data:
                setattr(db_obj, field, update_data[field])
        db.add(db_obj)

        t0 = time.perf_counter()
        await db.commit()
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.debug("DB update %s id=%s — commit took %.1f ms", self.model.__tablename__, db_obj.id, elapsed_ms)

        await db.refresh(db_obj)
        return db_obj

    async def remove(self, db: AsyncSession, *, id: str) -> ModelType:
        logger.debug("DB remove %s id=%s", self.model.__tablename__, id)
        obj = await db.get(self.model, id)
        await db.delete(obj)

        t0 = time.perf_counter()
        await db.commit()
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.debug("DB remove %s id=%s — commit took %.1f ms", self.model.__tablename__, id, elapsed_ms)

        return obj
    
class CRUDChat(
    CRUDBase[Chat, schemas.ChatCreate, schemas.ChatUpdate]
):
    pass

chat = CRUDChat(Chat)

class CRUDFormSubmission(
    CRUDBase[FormSubmission, schemas.FormSubmissionCreate, schemas.FormSubmissionUpdate]
):
    pass

form = CRUDFormSubmission(FormSubmission)


class CRUDChangeHistory(
    CRUDBase[ChangeHistory, schemas.ChangeHistoryCreate, schemas.ChangeHistoryCreate]
):
    """CRUD for the change_history table.

    Note: UpdateSchema is set to ChangeHistoryCreate since history rows are
    append-only and should never be updated, but the generic base requires
    the type parameter.
    """
    pass

change_history = CRUDChangeHistory(ChangeHistory)
