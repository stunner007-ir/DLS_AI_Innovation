import json
import os
import logging

logger = logging.getLogger(__name__)

def load_existing_events(filename: str):
    if os.path.exists(filename):
        try:
            with open(filename, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read {filename}: {e}")
    return []

def save_as_json(data, filename: str):
    try:
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving to {filename}: {e}")
