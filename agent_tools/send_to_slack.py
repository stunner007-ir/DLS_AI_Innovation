from langchain_core.tools import tool
import json
import requests
import os


SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID")


@tool
def send_to_slack(message: str) -> str:
    """
    Sends a message to a specific Slack channel.

    Args:
        message (str): The message to send to Slack.

    Returns:
        str: A message indicating whether the message was sent successfully or if there was an error.
    """
    slack_bot_token = SLACK_BOT_TOKEN
    slack_channel_id = SLACK_CHANNEL_ID

    if not slack_bot_token or not slack_channel_id:
        return "Error: SLACK_BOT_TOKEN or SLACK_CHANNEL_ID not set in environment variables."

    url = "https://slack.com/api/chat.postMessage"
    headers = {
        "Authorization": f"Bearer {slack_bot_token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    data = {
        "channel": slack_channel_id,
        "text": message,
    }
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        response.raise_for_status()
        result = response.json()
        if result.get("ok"):
            return f"Message sent to Slack successfully. \n  Try this Solution: {str(result)}"
        else:
            return f"Error sending message to Slack: {result.get('error')}"
    except requests.exceptions.RequestException as e:
        return f"Error sending message to Slack: {e}"
