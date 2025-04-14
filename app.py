import os
import time
import hmac
import hashlib
import json
import re
from typing import Dict, List
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from dotenv import load_dotenv
from agent import agent
from pydantic import BaseModel
import asyncio
from parse_slack_event.slack_parser import parse_slack_text  # Import the function
import uuid
from datetime import datetime, timezone


load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()

SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

SLACK_RESPONSE_FILE = "slack_response/slack_response.json"  # Define the file path
AGENT_RESPONSE_FILE = "agent_response/agent_response.json"  # Define the agent response file path


def load_existing_events(filename: str) -> List[Dict]:
    """Loads existing events from the JSON file."""
    try:
        if os.path.exists(filename):
            with open(filename, "r") as f:
                return json.load(f)
        else:
            return []
    except Exception as e:
        logger.error(f"Error loading existing events from {filename}: {e}")
        return []


def save_as_json(events: List[Dict], filename: str):
    """Saves the list of events to the JSON file."""
    try:
        with open(filename, "w") as f:
            json.dump(events, f, indent=2)
        logger.info(f"Events saved to {filename}")
    except Exception as e:
        logger.error(f"Error saving events to {filename}: {e}")


@app.post("/slack/events")
async def slack_events(request: Request):
    raw_body = await request.body()
    headers = request.headers

    # ✅ Verify the Slack signature
    if not verify_slack_signature(headers, raw_body):
        raise HTTPException(status_code=400, detail="Invalid Slack signature")

    try:
        data = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # ✅ Respond to Slack's URL verification
    if data.get("type") == "url_verification":
        return PlainTextResponse(content=data["challenge"])

    # ✅ Handle event callbacks
    event = data.get("event")

    if event and event.get("type") == "message":
        user = event.get("user")
        text = event.get("text")
        channel = event.get("channel")
        timestamp = event.get("ts")
        subtype = event.get("subtype", "user")

        parsed_text = parse_slack_text(text)  # Parse the text using the imported function

        message_data = {
            "id": str(uuid.uuid4()),  # Generate a unique ID
            "user": user,
            "channel": channel,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "subtype": subtype,
            "text_details": parsed_text
        }

        print("Incoming Slack Message:")
        print(json.dumps(message_data, indent=2))

        # Load existing events, add the new event at the beginning, and save
        existing_events = load_existing_events(SLACK_RESPONSE_FILE)
        if not isinstance(existing_events, list):
            existing_events = [existing_events]  # Ensure it's a list
        existing_events.insert(0, message_data)  # Add to the beginning
        save_as_json(existing_events, SLACK_RESPONSE_FILE)

        # ✅ Check if the message indicates a DAG failure
        if message_data["text_details"]["status"] == "failed":
            # Extract the DAG name using regex
            dag_name = message_data["text_details"].get("dag_name")  # Get dag name from parsed data

            if dag_name:
                logger.info(f"DAG failure detected for DAG: {dag_name}")

                # Call the agent to fetch logs (using asyncio.to_thread to avoid blocking)
                try:
                    response = await asyncio.to_thread(agent, f"fetch logs for dag {dag_name}")
                    logger.info(f"Agent response: {response}")

                    # Store the agent response
                    agent_response_data = {
                        "id": str(uuid.uuid4()),
                        "dag_name": dag_name,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "response": response
                    }

                    existing_agent_responses = load_existing_events(AGENT_RESPONSE_FILE)
                    if not isinstance(existing_agent_responses, list):
                        existing_agent_responses = [existing_agent_responses]
                    existing_agent_responses.insert(0, agent_response_data)
                    save_as_json(existing_agent_responses, AGENT_RESPONSE_FILE)

                    # TODO:  Potentially post the response back to the Slack channel

                except Exception as e:
                    logger.error(f"Error calling agent: {e}")
                    response = f"Error fetching logs: {e}"  # Provide an error message

            # Return a response to Slack (can be improved to post the logs)
            return JSONResponse(
                content={"status": "ok",
                         "message": f"DAG failure detected.  Attempted to fetch logs for {dag_name}. Check logs and {AGENT_RESPONSE_FILE} for agent response."})

        # You can process/save the message here if needed
        # For example: store to DB, send to webhook, etc.

        return JSONResponse(content={"status": "ok"})


def write_json_to_file(data: dict, filename: str):
    """Writes JSON data to a file."""
    try:
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Error writing to file in separate thread: {e}")


def verify_slack_signature(headers: Dict[str, str], raw_body: bytes) -> bool:
    slack_signature = headers.get("X-Slack-Signature")
    slack_timestamp = headers.get("X-Slack-Request-Timestamp")

    if not slack_signature or not slack_timestamp:
        return False

    try:
        slack_timestamp = float(slack_timestamp)
    except ValueError:
        return False

    # Slack allows max 5 min delay
    if abs(time.time() - slack_timestamp) > 60 * 5:
        return False

    sig_basestring = f"v0:{int(slack_timestamp)}:{raw_body.decode('utf-8')}"
    my_signature = "v0=" + hmac.new(
        SLACK_SIGNING_SECRET.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(my_signature, slack_signature)


class QueryRequest(BaseModel):
    query: str


@app.post("/query")
async def handle_query(request: QueryRequest):
    try:
        response = agent(request.query)
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Run with: python main.py
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
