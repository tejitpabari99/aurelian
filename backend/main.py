from typing import Any, AsyncGenerator, Optional
import json
import logging
import time
import uuid, os


from fastapi import Depends, FastAPI, HTTPException, Request
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

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

openai_client = OpenAI(api_key=os.getenv("OPENAI_KEY"))

SYSTEM_TEMPLATE = """You are a helpful assistant that can manage interest form submissions.

You have the following tools available:
- submit_interest_form: Collect and submit a new interest form with name, email, and phone number.
- update_form_submission: Update an existing form submission by its ID. You can update name, email, phone_number, and status (1=TO DO, 2=IN PROGRESS, 3=COMPLETED, or null to clear).
- delete_form_submission: Delete an existing form submission by its ID.

When a user wants to update or delete a form, you will need the form's ID. If the user does not provide it, ask them for it. The form ID was provided when the form was originally submitted.
"""

TOOLS = [
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
                "required": ["name", "email", "phone_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_form_submission",
            "description": "Update an existing form submission. Can update the name, email, phone number, and/or status. Status must be 1 (TO DO), 2 (IN PROGRESS), or 3 (COMPLETED), or null to clear it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "form_id": {
                        "type": "string",
                        "description": "the ID of the form submission to update",
                    },
                    "name": {
                        "type": "string",
                        "description": "the updated name (optional)",
                    },
                    "email": {
                        "type": "string",
                        "description": "the updated email address (optional)",
                    },
                    "phone_number": {
                        "type": "string",
                        "description": "the updated phone number (optional)",
                    },
                    "status": {
                        "type": ["integer", "null"],
                        "description": "the updated status: 1 = TO DO, 2 = IN PROGRESS, 3 = COMPLETED, or null to clear",
                    },
                },
                "required": ["form_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_form_submission",
            "description": "Delete an existing form submission by its ID",
            "parameters": {
                "type": "object",
                "properties": {
                    "form_id": {
                        "type": "string",
                        "description": "the ID of the form submission to delete",
                    },
                },
                "required": ["form_id"],
            },
        },
    },
]

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
    logger.info("GET /chat — listing chats")
    chats = await crud.chat.get_multi(
        db, limit=10,
        options=[selectinload(models.Chat.form_submissions)]
    )
    logger.info("GET /chat — returning %d chats", len(chats))
    return chats

# the data parameter represents the body of the request. The request body should always be in JSON format
@app.post("/chat", response_model=schemas.Chat)
async def create_chat(data: schemas.ChatCreate, db: AsyncSession = Depends(get_db)):
    logger.info("POST /chat — creating new chat")
    chat = await crud.chat.create(db=db, obj_in=data)
    logger.info("POST /chat — created chat id=%s", chat.id)
    # Re-fetch with form_submissions eager-loaded for the response
    chat = await crud.chat.get(
        db, id=chat.id,
        options=[selectinload(models.Chat.form_submissions)]
    )
    return chat

# the chat_id parameter maps to the chat id in the URL
@app.put("/chat/{chat_id}", response_model=schemas.Chat)
async def update_chat(
    chat_id: str, data: schemas.ChatUpdate, db: AsyncSession = Depends(get_db)
):
    logger.info("PUT /chat/%s — processing %d messages", chat_id, len(data.messages))
    chat = await crud.chat.get(db, id=chat_id)
    if chat is None:
        logger.warning("Chat not found: chat_id=%s", chat_id)
        raise HTTPException(status_code=404, detail="Chat not found")

    # --- First OpenAI call (potential bottleneck) ---
    t0 = time.perf_counter()
    resp = openai_client.chat.completions.create(
        messages=[{"role": "system", "content": SYSTEM_TEMPLATE}] + data.messages,
        model="gpt-4o-mini",
        tools=TOOLS,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000
    resp_message = resp.choices[0].message.model_dump()
    logger.debug("PUT /chat/%s — OpenAI call 1 took %.0f ms", chat_id, elapsed_ms)

    data.messages.append(resp_message)

    if resp_message.get('tool_calls'):
        num_tool_calls = len(resp_message["tool_calls"])
        logger.info("PUT /chat/%s — %d tool call(s) received", chat_id, num_tool_calls)

        for t in resp_message["tool_calls"]:
            tool_name = t["function"]["name"]
            tool_content = "Success"

            if tool_name == "submit_interest_form":
                try:
                    args = json.loads(t["function"]["arguments"])
                    logger.debug("PUT /chat/%s — parsed form args: name=%s, email=%s", chat_id, args.get("name"), args.get("email"))

                    form_data = schemas.FormSubmissionCreate(
                        name=args.get("name", ""),
                        email=args.get("email", ""),
                        phone_number=args.get("phone_number", ""),
                        chat_id=chat_id,
                    )

                    created_form = await crud.form.create(db=db, obj_in=form_data)
                    logger.info(
                        "FormSubmission created: id=%s, chat_id=%s, name=%s",
                        created_form.id, chat_id, form_data.name,
                    )
                    tool_content = f"Success. Form submission ID: {created_form.id}"

                except json.JSONDecodeError as e:
                    logger.error("Failed to parse tool call arguments: %s", e)
                    tool_content = "Error: Could not parse form data"
                except Exception as e:
                    logger.error("Failed to create FormSubmission: %s", e, exc_info=True)
                    tool_content = "Error: Failed to save form"

            elif tool_name == "update_form_submission":
                try:
                    args = json.loads(t["function"]["arguments"])
                    form_id = args.get("form_id")
                    if not form_id:
                        tool_content = "Error: form_id is required"
                    else:
                        form = await crud.form.get(db, id=form_id)
                        if form is None:
                            tool_content = f"Error: Form submission with ID {form_id} not found"
                        else:
                            # Only include fields the LLM actually provided to avoid
                            # overwriting existing values with None via exclude_unset
                            update_fields = {}
                            for key in ("name", "email", "phone_number", "status"):
                                if key in args:
                                    update_fields[key] = args[key]
                            update_data = schemas.FormSubmissionUpdate(**update_fields)
                            updated_form = await crud.form.update(db, db_obj=form, obj_in=update_data)
                            logger.info(
                                "FormSubmission updated via chat: id=%s, chat_id=%s",
                                updated_form.id, chat_id,
                            )
                            tool_content = f"Success. Form submission {form_id} has been updated."
                except json.JSONDecodeError as e:
                    logger.error("Failed to parse update tool call arguments: %s", e)
                    tool_content = "Error: Could not parse update data"
                except ValueError as e:
                    logger.error("Validation error on form update: %s", e)
                    tool_content = f"Error: {e}"
                except Exception as e:
                    logger.error("Failed to update FormSubmission: %s", e, exc_info=True)
                    tool_content = f"Error: Failed to update form — {e}"

            elif tool_name == "delete_form_submission":
                try:
                    args = json.loads(t["function"]["arguments"])
                    form_id = args.get("form_id")
                    if not form_id:
                        tool_content = "Error: form_id is required"
                    else:
                        form = await crud.form.get(db, id=form_id)
                        if form is None:
                            tool_content = f"Error: Form submission with ID {form_id} not found"
                        else:
                            await crud.form.remove(db, id=form_id)
                            logger.info(
                                "FormSubmission deleted via chat: id=%s, chat_id=%s",
                                form_id, chat_id,
                            )
                            tool_content = f"Success. Form submission {form_id} has been deleted."
                except json.JSONDecodeError as e:
                    logger.error("Failed to parse delete tool call arguments: %s", e)
                    tool_content = "Error: Could not parse delete data"
                except Exception as e:
                    logger.error("Failed to delete FormSubmission: %s", e, exc_info=True)
                    tool_content = f"Error: Failed to delete form — {e}"

            else:
                logger.debug("PUT /chat/%s — skipping unknown tool call: %s", chat_id, tool_name)

            data.messages.append(
                {
                    "tool_call_id": t["id"],
                    "role": "tool",
                    "name": tool_name,
                    "content": tool_content,
                }
            )

        # --- Second OpenAI call after tool responses (potential bottleneck) ---
        t0 = time.perf_counter()
        resp = openai_client.chat.completions.create(
            messages=[{"role": "system", "content": SYSTEM_TEMPLATE}] + data.messages,
            model="gpt-4o-mini",
            tools=TOOLS,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        resp_message = resp.choices[0].message.model_dump()
        logger.debug("PUT /chat/%s — OpenAI call 2 (post-tool) took %.0f ms", chat_id, elapsed_ms)

        data.messages.append(resp_message)

    chat = await crud.chat.update(db, db_obj=chat, obj_in=data)

    # Re-fetch with form_submissions eager-loaded for the response
    chat = await crud.chat.get(
        db, id=chat_id,
        options=[selectinload(models.Chat.form_submissions)]
    )
    logger.info("PUT /chat/%s — done, %d messages total", chat_id, len(data.messages))

    return chat


@app.get("/chat/{chat_id}", response_model=schemas.Chat)
async def get_chat(chat_id: str, db: AsyncSession = Depends(get_db)):
    logger.info("GET /chat/%s", chat_id)
    chat = await crud.chat.get(
        db, id=chat_id,
        options=[selectinload(models.Chat.form_submissions)]
    )
    if chat is None:
        logger.warning("Chat not found: chat_id=%s", chat_id)
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


@app.get("/chat/{chat_id}/forms", response_model=list[schemas.FormSubmission])
async def get_chat_forms(
    chat_id: str,
    status: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    logger.info("GET /chat/%s/forms — status filter=%s", chat_id, status)
    filters = [models.FormSubmission.chat_id == chat_id]
    if status is not None:
        filters.append(models.FormSubmission.status == status)
    forms = await crud.form.get_multi(db, filters=filters)
    logger.info("GET /chat/%s/forms — returning %d forms", chat_id, len(forms))
    return forms


# ---------------------------------------------------------------------------
# Form Submission REST endpoints
# ---------------------------------------------------------------------------

@app.put("/form/{form_id}", response_model=schemas.FormSubmission)
async def update_form(
    form_id: str,
    data: schemas.FormSubmissionUpdate,
    db: AsyncSession = Depends(get_db),
):
    logger.info("PUT /form/%s — updating form", form_id)
    form = await crud.form.get(db, id=form_id)
    if form is None:
        logger.warning("Form not found: form_id=%s", form_id)
        raise HTTPException(status_code=404, detail="Form submission not found")

    updated_form = await crud.form.update(db, db_obj=form, obj_in=data)
    logger.info("PUT /form/%s — updated successfully", form_id)
    return updated_form


@app.delete("/form/{form_id}", response_model=schemas.FormSubmission)
async def delete_form(
    form_id: str,
    db: AsyncSession = Depends(get_db),
):
    logger.info("DELETE /form/%s — deleting form", form_id)
    form = await crud.form.get(db, id=form_id)
    if form is None:
        logger.warning("Form not found: form_id=%s", form_id)
        raise HTTPException(status_code=404, detail="Form submission not found")

    deleted_form = await crud.form.remove(db, id=form_id)
    logger.info("DELETE /form/%s — deleted successfully", form_id)
    return deleted_form
