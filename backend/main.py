from typing import Any, AsyncGenerator
import json
import uuid, os


from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from dotenv import load_dotenv

import crud
from database import SessionLocal
import models
import schemas

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

openai_client = OpenAI(api_key=os.getenv("OPENAI_KEY"))

SYSTEM_TEMPLATE = """"""

# Get a DB Session
async def get_db() -> AsyncGenerator:
    async with SessionLocal() as session:
        yield session


@app.get("/")
async def root():
    return {"message": "Hello World"}

# response_model represents the format of the response that this endpoint will produce. Responses are always in JSON
@app.get("/chat", response_model=list[schemas.Chat])
async def get_chats(db: AsyncSession = Depends(get_db)):
    chats = await crud.chat.get_multi(
        db, limit=10,
        options=[selectinload(models.Chat.form_submissions)]
    )
    return chats

# the data parameter represents the body of the request. The request body should always be in JSON format
@app.post("/chat", response_model=schemas.Chat)
async def create_chat(data: schemas.ChatCreate, db: AsyncSession = Depends(get_db)):
    chat = await crud.chat.create(db=db, obj_in=data)
    return chat

# the chat_id parameter maps to the chat id in the URL
@app.put("/chat/{chat_id}", response_model=schemas.Chat)
async def update_chat(
    chat_id: str, data: schemas.ChatUpdate, db: AsyncSession = Depends(get_db)
):
    chat = await crud.chat.get(db, id=chat_id)

    resp = openai_client.chat.completions.create(
        messages=[{"role": "system", "content": SYSTEM_TEMPLATE}] + data.messages,
        model="gpt-4o-mini",
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "submit_interest_form",
                    "description": "Submit an interest form for the user with the given properties",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "the user's name",
                            },
                            "email": {
                                "type": "string",
                                "description": "the user's email address",
                            },
                            "phone_number": {
                                "type": "string",
                                "description": "the user's phone number",
                            },
                        },
                    },
                },
            }
        ],
    )
    resp_message = resp.choices[0].message.model_dump()

    data.messages.append(resp_message)

    if resp_message.get('tool_calls'):
        for t in resp_message["tool_calls"]:
            tool_name = t["function"]["name"]
            tool_content = "Success"

            if tool_name == "submit_interest_form":
                try:
                    args = json.loads(t["function"]["arguments"])

                    form_data = schemas.FormSubmissionCreate(
                        name=args.get("name", ""),
                        email=args.get("email", ""),
                        phone_number=args.get("phone_number", ""),
                        chat_id=chat_id,
                    )

                    created_form = await crud.form.create(db=db, obj_in=form_data)
                    tool_content = f"Success. Form submission ID: {created_form.id}"

                except json.JSONDecodeError:
                    tool_content = "Error: Could not parse form data"
                except Exception:
                    tool_content = "Error: Failed to save form"

            data.messages.append(
                {
                    "tool_call_id": t["id"],
                    "role": "tool",
                    "name": tool_name,
                    "content": tool_content,
                }
            )

        resp = openai_client.chat.completions.create(
            messages=[{"role": "system", "content": SYSTEM_TEMPLATE}] + data.messages,
            model="gpt-4o-mini",
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "submit_interest_form",
                        "description": "Submit an interest form for the user with the given properties",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "the user's name",
                                },
                                "email": {
                                    "type": "string",
                                    "description": "the user's email address",
                                },
                                "phone_number": {
                                    "type": "string",
                                    "description": "the user's phone number",
                                },
                            },
                        },
                    },
                }
            ],
        )
        resp_message = resp.choices[0].message.model_dump()

        data.messages.append(resp_message)

    chat = await crud.chat.update(db, db_obj=chat, obj_in=data)

    # Re-fetch with form_submissions eager-loaded for the response
    chat = await crud.chat.get(
        db, id=chat_id,
        options=[selectinload(models.Chat.form_submissions)]
    )

    return chat


@app.get("/chat/{chat_id}", response_model=schemas.Chat)
async def get_chat(chat_id: str, db: AsyncSession = Depends(get_db)):
    chat = await crud.chat.get(
        db, id=chat_id,
        options=[selectinload(models.Chat.form_submissions)]
    )

    return chat


@app.get("/chat/{chat_id}/forms", response_model=list[schemas.FormSubmission])
async def get_chat_forms(chat_id: str, db: AsyncSession = Depends(get_db)):
    forms = await crud.form.get_multi(
        db, filters=[models.FormSubmission.chat_id == chat_id]
    )
    return forms
