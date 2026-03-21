import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar, Union

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Base, Chat, FormSubmission
import schemas

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
        statement = select(self.model).filter(self.model.id == id).options(*options)
        result = await db.scalars(statement)
        return result.first()

    async def get_multi(
        self, db: AsyncSession, *, filters: list = [], skip: int = 0, limit: int = 100, options: list = []
    ) -> List[ModelType]:
        statement = select(self.model).filter(*filters).options(*options).offset(skip).limit(limit)
        result = await db.scalars(statement)
        return result.all()

    async def create(self, db: AsyncSession, *, obj_in: CreateSchemaType) -> ModelType:
        obj_in_data = jsonable_encoder(obj_in)
        db_obj = self.model(
            **obj_in_data, created_at=datetime.now(timezone.utc).replace(tzinfo=None)
        )  # type: ignore

        db.add(db_obj)

        await db.commit()
        await db.refresh(db_obj)
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
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def remove(self, db: AsyncSession, *, id: str) -> ModelType:
        obj = await db.get(self.model, id)
        await db.delete(obj)
        await db.commit()
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