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
from agent_handler.agent import agent
from pydantic import BaseModel
import asyncio
from parse_slack_event.slack_parser import parse_slack_text  # Import the function
import uuid
import queue  # Import the queue module
from threading import Thread  # Import the Thread module

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')  # Corrected logging format
logger = logging.getLogger(__name__)

app = FastAPI()

SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

SLACK_RESPONSE_FILE = "slack_response/slack_response.json"  # Define the file path
AGENT_RESPONSE_FILE = "agent_response/agent_response.json"  # Define the agent response file path

# In-memory set to store processed timestamps (for duplicate detection within session)
processed_timestamps = set()

# Queue for asynchronous event processing
event_queue = queue.Queue()

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

def save_events(events: List[Dict], filename: str):
    """Saves the list of events to the JSON file."""
    try:
        with open(filename, "w") as f:
            json.dump(events, f, indent=2)
        logger.info(f"Events saved to {filename}")
    except Exception as e:
        logger.error(f"Error saving events to {filename}: {e}")

# Function to process events from the queue
def process_event(event_data: Dict):
    try:
        text = event_data.get("text")
        timestamp = event_data.get("timestamp")

        parsed_text = parse_slack_text(text)  # Parse the text using the imported function
        event_data["text_details"] = parsed_text

        print("🟢 Processing Slack Message:")
        print(json.dumps(event_data, indent=2))

        # ✅ Check if the message indicates a DAG failure
        if event_data["text_details"]["status"] == "failed":
            print("hhhhhhhhhhhhhhh")
            # Extract the DAG name using regex
            dag_name = event_data["text_details"].get("dag_name")  # Get dag name from parsed data

            if dag_name:
                logger.info(f"DAG failure detected for DAG: {dag_name}")

                # Call the agent to fetch logs (using asyncio.to_thread to avoid blocking)
                try:
                    response = asyncio.run(asyncio.to_thread(agent, f"fetch logs for dag {dag_name}"))  # Run async in sync context
                    logger.info(f"Agent response: {response}")

                    # Store the agent response
                    agent_response_data = {
                        "id": str(uuid.uuid4()),
                        "dag_name": dag_name,
                        "timestamp": time.time(),
                        "response": response
                    }

                    existing_agent_responses = load_existing_events(AGENT_RESPONSE_FILE)
                    if not isinstance(existing_agent_responses, list):
                        existing_agent_responses = [existing_agent_responses]
                    existing_agent_responses.insert(0, agent_response_data)
                    save_events(existing_agent_responses, AGENT_RESPONSE_FILE)

                    # TODO:  Potentially post the response back to the Slack channel

                except Exception as e:
                    logger.error(f"Error calling agent: {e}")
                    response = f"Error fetching logs: {e}"  # Provide an error message

    except Exception as e:
        logger.error(f"Error processing event: {e}")

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

        # ✅ Check for retry headers
        retry_num = headers.get("X-Slack-Retry-Num")
        retry_reason = headers.get("X-Slack-Retry-Reason")
        if retry_num:
            logger.warning(f"Received retry attempt {retry_num} with reason: {retry_reason}")

        # ✅ Check if the message has already been processed (in-memory)
        if timestamp in processed_timestamps:
            logger.info(f"Duplicate message detected with timestamp: {timestamp}. Skipping.")
            return JSONResponse(content={"status": "ok", "message": "Duplicate message. Skipped."})

        # Add the timestamp to the set of processed timestamps
        processed_timestamps.add(timestamp)

        message_data = {
            "id": str(uuid.uuid4()),  # Generate a unique ID
            "user": user,
            "channel": channel,
            "timestamp": timestamp,
            "subtype": subtype,
            "text": text  # Store the original text here
        }

        # Put the event data into the queue for asynchronous processing
        event_queue.put(message_data)

        # Immediately return a 200 OK response to Slack
        return JSONResponse(content={"status": "ok", "message": "Event received and queued for processing."})

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

# Start the event processing thread
def start_event_processor():
    while True:
        try:
            event_data = event_queue.get()
            process_event(event_data)
            event_queue.task_done()
        except Exception as e:
            logger.error(f"Error in event processing thread: {e}")
            time.sleep(1)  # Add a small delay to prevent busy-looping

event_processing_thread = Thread(target=start_event_processor, daemon=True)
event_processing_thread.start()

# Run with: python main.py
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
