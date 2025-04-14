import json
import uuid
import asyncio
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from datetime import datetime, timezone
import logging

from config import SLACK_SIGNING_SECRET, SLACK_RESPONSE_FILE, AGENT_RESPONSE_FILE
from agent_handler.handler import agent
from slack_handler.utils import load_existing_events, save_as_json
from slack_handler.verifier import verify_slack_signature
from parse_slack_event.slack_parser import parse_slack_text

logger = logging.getLogger(__name__)
slack_events = APIRouter()


@slack_events.post("/events")
async def handle_slack_event(request: Request):
    raw_body = await request.body()
    headers = request.headers

    if not verify_slack_signature(headers, raw_body):
        raise HTTPException(status_code=400, detail="Invalid Slack signature")

    try:
        data = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if data.get("type") == "url_verification":
        return PlainTextResponse(content=data["challenge"])

    event = data.get("event")
    if event and event.get("type") == "message":
        user = event.get("user")
        text = event.get("text")
        channel = event.get("channel")
        subtype = event.get("subtype", "user")
        timestamp = datetime.now(timezone.utc).isoformat()

        parsed_text = parse_slack_text(text)

        message_data = {
            "id": str(uuid.uuid4()),
            "user": user,
            "channel": channel,
            "timestamp": timestamp,
            "subtype": subtype,
            "text_details": parsed_text,
        }

        logger.info("Incoming Slack Message: %s", json.dumps(message_data, indent=2))
        print("Incoming Slack Message:")
        print(json.dumps(message_data, indent=2))

        existing_events = load_existing_events(SLACK_RESPONSE_FILE)
        existing_events.insert(0, message_data)
        save_as_json(existing_events, SLACK_RESPONSE_FILE)

        if parsed_text.get("status") == "failed":
            dag_name = parsed_text.get("dag_name")
            print(dag_name)

            if dag_name:
                logger.info(f"DAG failure detected: {dag_name}")
                try:
                    response = await asyncio.to_thread(
                        agent, f"fetch logs for dag {dag_name}"
                    )
                except Exception as e:
                    logger.error(f"Agent error: {e}")
                    response = f"Error fetching logs: {e}"

                agent_response_data = {
                    "id": str(uuid.uuid4()),
                    "dag_name": dag_name,
                    "timestamp": timestamp,
                    "response": response,
                }

                agent_responses = load_existing_events(AGENT_RESPONSE_FILE)
                agent_responses.insert(0, agent_response_data)
                save_as_json(agent_responses, AGENT_RESPONSE_FILE)

            return JSONResponse(
                content={"status": "ok", "message": f"Fetched logs for {dag_name}"}
            )

    return JSONResponse(content={"status": "ok"})
