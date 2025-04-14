from fastapi import FastAPI
from dotenv import load_dotenv
from slack_handler.events import slack_events
from agent_handler.handler import handle_query

load_dotenv()

app = FastAPI()

app.include_router(slack_events, prefix="/slack")
app.include_router(handle_query, prefix="/query")

# Run with: uvicorn main:app --reload
