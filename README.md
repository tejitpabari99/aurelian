# Aurelian Take Home Assessment

## AI Usage

Since we cannot enforce a no AI policy for a take-home, you are allowed to use AI tools on this assessment. HOWEVER, please disclose any usage of AI tools in a file called AI.md and explain where you chose to use AI.

## Expectations

Your priority is to complete as much of the tasks as possible while maintaining a high bar for quality. If you find the requirements or specifications unclear at any point, leave comments in your code about the assumptions you made.

## Overview

We have provided you with a basic prototype of an AI chat application. The application has the ability to create chats and chat back and forth with the user.

Right now, the agent is extremely basic, pretty much just a vanilla version of ChatGPT with one additional function - the ability to collect interest forms. Your tasks will revolve around fleshing out this ability by saving interest forms to the database, and creating APIs and UIs to get and edit these interest forms.

## Tips

### Backend

Database tables are modeled in models.py - each class represents a table.

For APIs, see the endpoints in main.py. You can also visit http://localhost:8000/docs after running the backend server for simple documentation of each API endpoint. By looking at this documentation and the existing endpoints, you should be able to figure out how the API works. You can also look at the FastAPI documentation on the web for additional help.

There are also prebuilt CRUD functions for all database models already in crud.py. The best way to understand how to use these functions is to probably look at the existing POST /chat and PUT /chat/{chat_id} routes.

### Frontend

The frontend does require some knowledge of React but shouldn't require much knowledge of NextJS, if any. All you should need to know is that the different pages of the app can be found under the "app" folder. "page.tsx" generally represents the code for that page. Subfolders map to subroutes, so app/[chatId]/page.tsx would be the code for /[chatId] where chat ID is the ID of a given chat. Similarly, app/page.tsx is the code for /.

Again, we strongly recommend looking at and copying patterns from the existing code to make your job easier. Many common patterns such as getting data or sending POST requests may already have similar implementations. Remember these tasks are meant to be representative of working as a full stack engineer in an existing code base, so we encourage you to complete them as you would your normal work.

If you are completely unfamiliar with React, you can write the needed components in the framework of your choice as long as you let us know what framework you used and where to find your code. However, we would prefer you use React if at all possible.

## Getting Setup

Before doing anything else, paste the API key you were provided into backend/main.py where it says "YOUR_KEY_HERE"

### Backend/Database

```bash
cd backend

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

alembic upgrade head
uvicorn main:app --reload
```

### Frontend

```bash
cd frontend

npm i

npm run dev
```

## Task 1 - Collect Structured Interest Form

The AI agent has a tool to collect an interest form. If a user requests to submit an interest form, the agent will ask for the required information, and then use the tool. Right now, the tool doesnt actually do anything. It just returns success.

Your task is to update the "update_chat" function in main.py so that the tool actually does something. Specifically, we want the tool to use the collected information to create a FormSubmission row in the database for each collected interest form. A database model and basic CRUD operations have already been provided for FormSubmissions for you to use.

To save you some time, you may find the capabilities section of the OpenAI docs to be helpful in understanding what the tool call schema looks like: https://platform.openai.com/docs/guides/function-calling?api-mode=chat

After you are able to successfully create FormSubmissions, update the UI and API to display all interest forms submitted during a particular chat in the chat UI. If I open a chat, I want to still see the chat window with all the messages, as well as a list of forms that were submitted as part of that particular chat. It is your discretion how to design the API and UI to accomodate this. For the sake of time, don't worry about how pretty your UI is - as long as it displays the data in a useful way, it's fine.

## Task 2 - Add additional functionality to the chat bot and API

We want to allow users to additionally update their form submissions and delete their form submissions via the chat interface. Augment the chat endpoint with additional logic to support this.

We will eventually want to be able to update the form submissions via the UI as well. Flesh out the REST API for working with FormSubmissions. Include at least the following endpoints and requirements:

1. Update a form submission. Should be able to update name, email, phone number, and status. Add a way to validate the status field. It should be either None, 1, 2, or 3. 1 = "TO DO", 2 = "IN PROGRESS", 3 = "COMPLETED"
2. Get all form submissions for a specific chat. Should be able to filter by status
3. Delete a form submission.

## Task 3 - Change History Design

We want to be able to track the full revision history of a Form Submission and all changes made after each update. Design a data model that would allow us to do this. Consider that in the future we may want to track the revision history of other things using this same model. The ability to filter by certain properties is not as important here. We just want to be able to determine what fields changed, what changed about them, and when they changed. No need to write code for this portion. Just include the details of your model and thought process in a file called task3.md
