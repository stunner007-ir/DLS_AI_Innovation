import os
import time
import hmac
import hashlib
import json
import re
from typing import Dict
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from dotenv import load_dotenv
from agent_handler.agent import agent  # Import the agent function
from pydantic import BaseModel
import asyncio  # Import asyncio

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()

SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

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

        print("Incoming Slack Message:")
        print(json.dumps({
            "user": user,
            "text": text,
            "channel": channel,
            "timestamp": timestamp,
            "subtype": subtype
        }, indent=2))

        # ✅ Check if the message indicates a DAG failure
        if ":red_circle: Task" in text and "failed" in text and "DAG:" in text:
            # Extract the DAG name using regex
            dag_name_match = re.search(r"DAG: \*(.*?)\*", text)
            if dag_name_match:
                dag_name = dag_name_match.group(1)
                logger.info(f"DAG failure detected for DAG: {dag_name}")

                # Call the agent to fetch logs (using asyncio.to_thread to avoid blocking)
                try:
                    # response = agent(f"fetch logs for dag {dag_name}")
                    response = await asyncio.to_thread(agent, f"fetch logs for dag {dag_name}")
                    logger.info(f"Agent response: {response}")
                    # TODO:  Potentially post the response back to the Slack channel
                except Exception as e:
                    logger.error(f"Error calling agent: {e}")
                    response = f"Error fetching logs: {e}"  # Provide an error message

                # Return a response to Slack (can be improved to post the logs)
                return JSONResponse(content={"status": "ok", "message": f"DAG failure detected.  Attempted to fetch logs for {dag_name}. Check logs for agent response."})

        # You can process/save the message here if needed
        # For example: store to DB, send to webhook, etc.

        return JSONResponse(content={"status": "ok"})


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
