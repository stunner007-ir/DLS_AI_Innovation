import json
import uuid
import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse

from config import SLACK_SIGNING_SECRET, SLACK_RESPONSE_FILE, AGENT_RESPONSE_FILE
from agent_handler.handler import agent
from slack_handler.utils import load_existing_events, save_as_json, parse_slack_text
from slack_handler.verifier import verify_slack_signature

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)
slack_events = APIRouter()


@slack_events.post("/events")
async def handle_slack_event(request: Request):
    """
    Handles incoming Slack events, verifies the signature, parses the event,
    checks for duplicates, and triggers the agent if necessary.
    """
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

    # print("Event data:")
    # print(json.dumps(event, indent=2))

    # Check if the event is a message
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
        # print("Message data:")
        # print(json.dumps(message_data, indent=2))  # Log the message data

        # Duplicate Check Logic
        # dag_name = parsed_text.get("dag_name")
        # run_date = parsed_text.get("run_date")

        dag_name = message_data.get("text_details", {}).get("dag_name")
        run_date = message_data.get("text_details", {}).get("run_date")

        if dag_name and run_date:
            existing_events = load_existing_events(SLACK_RESPONSE_FILE)
            is_duplicate = any(
                event["text_details"].get("dag_name") == dag_name
                and event["text_details"].get("run_date") == run_date
                for event in existing_events
            )

            if is_duplicate:
                logger.info(
                    f"Duplicate event detected for DAG: {dag_name}, Run Date: {run_date}. Ignoring."
                )
                return JSONResponse(
                    content={
                        "status": "ok",
                        "message": "Duplicate event.  No action taken.",
                    }
                )
            else:
                logger.info(
                    "Incoming Slack Message: %s", json.dumps(message_data, indent=2)
                )  # Log only if not duplicate

        else:
            logger.info(
                "Incoming Slack Message: %s", json.dumps(message_data, indent=2)
            )  # Log if dag_name or run_date is missing

        # Save the message (if not a duplicate or if dag_name/run_date are missing)
        existing_events = load_existing_events(SLACK_RESPONSE_FILE)
        existing_events.insert(0, message_data)
        save_as_json(existing_events, SLACK_RESPONSE_FILE)

        # Agent Trigger Logic (only if DAG failed and not a duplicate)
        if message_data.get("text_details", {}).get("status") == "failed" and dag_name:
            # if message_data.get("status") == "failed" and dag_name:
            # if parsed_text.get("status") == "failed" and dag_name:
            logger.info(f"DAG failure detected: {dag_name}")
            try:
                # Fetch the DaG details
                print("Fetching DAG details...")
                dag_details = await asyncio.to_thread(
                    agent,
                    f"Use the DAG Details Fetching Tool to get information for the DAG named '{dag_name}'.",
                )

                logger.info(f"DAG details fetched: {json.dumps(dag_details, indent=2)}")

                # print("Saving DAG details to JSON...")
                # save_dag_details_result = await asyncio.to_thread(
                #     agent,
                #     f"Now save the fetched DAG details to a JSON file. This is the DAG details: {dag_details}",
                # )

                # logger.info(f"DAG details saved to JSON: {save_dag_details_result}")
                print("Fetching logs...")
                logs = await asyncio.to_thread(
                    agent,
                    f"Use the Log Fetching Tool to get logs for the DAG '{dag_name}'.",
                )

                # Then, analyze the logs
                print("Analyzing logs...")
                analysis = await asyncio.to_thread(
                    agent,
                    f"Use the Log Analysis Tool. Analyze these logs for DAG '{dag_name}' and give a summary: {logs}",
                )

                # Send the analysis to Slack
                print("Sending analysis to Slack...")
                slack_message_result = await asyncio.to_thread(
                    agent,
                    f"Send a Slack message about an error in DAG '{dag_name}'. Use this analysis: {analysis}",
                )

            except Exception as e:
                logger.error(f"Agent error: {e}")
                logs = f"Error fetching logs: {e}"
                analysis = f"Error analyzing logs: {e}"
                slack_message_result = f"Error sending message to Slack: {e}"

            agent_response_data = {
                "id": str(uuid.uuid4()),
                "dag_name": dag_name,
                "timestamp": timestamp,
                "dag_details": dag_details,
                "logs": logs,
                "analysis": analysis,
                "slack_message_result": slack_message_result,
            }

            agent_responses = load_existing_events(AGENT_RESPONSE_FILE)
            agent_responses.insert(0, agent_response_data)
            save_as_json(agent_responses, AGENT_RESPONSE_FILE)

            return JSONResponse(
                content={
                    "status": "ok",
                    "message": f"Fetched logs and analysis for {dag_name}",
                    "dag_details": dag_details,
                    "logs": logs,
                    "analysis": analysis,
                    "slack_message_result": slack_message_result,
                }
            )

        return JSONResponse(content={"status": "ok"})  # Normal message processing

    return JSONResponse(content={"status": "ok"})  # Non-message event
