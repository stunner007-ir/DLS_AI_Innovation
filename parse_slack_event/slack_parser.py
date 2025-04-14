import re
import logging
from typing import Dict

logger = logging.getLogger(__name__)


def parse_slack_text(text: str) -> Dict:
    """Parses Slack message text and extracts Airflow alert info."""
    try:
        # Normalize text: remove leading/trailing whitespace
        cleaned_text = text.strip()

        # Extract DAG name
        dag_name_match = re.search(r"DAG \*(.*?)\*", cleaned_text)
        dag_name = dag_name_match.group(1) if dag_name_match else None

        # Extract Run ID
        run_id_match = re.search(r"Run ID: \*(.*?)\*", cleaned_text)
        run_id = run_id_match.group(1) if run_id_match else None

        # Extract Run Date
        run_date_match = re.search(r"Run Date: \*(.*?)\*", cleaned_text)
        run_date = run_date_match.group(1) if run_date_match else None

        # Extract Status (based on presence of "failed!" or "succeeded!")
        if "failed" in cleaned_text.lower():
            status = "failed"
        elif "success" in cleaned_text.lower() or "succeeded" in cleaned_text.lower():
            status = "success"
        else:
            status = "unknown"

        return {
            "dag_name": dag_name,
            "run_id": run_id,
            "run_date": run_date,
            "status": status,
            "full_text": text,  # include original message for logging/reference
        }

    except Exception as e:
        logger.error(f"Error parsing Slack text: {e}")
        return {"error": str(e), "full_text": text}
