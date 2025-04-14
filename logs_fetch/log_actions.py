import requests
import json
import os
from dotenv import load_dotenv
from langchain_core.tools import tool

# Load environment variables
load_dotenv()

AIRFLOW_URL = "http://localhost:8080"
USERNAME = "airflow"
PASSWORD = "airflow"

# Define the directory to save the JSON file
OUTPUT_DIR = "logs/output"
OUTPUT_FILE = "agent_output.json"


def fetch_dags() -> list:
    url = f"{AIRFLOW_URL}/api/v1/dags"
    try:
        response = requests.get(url, auth=(USERNAME, PASSWORD))
        response.raise_for_status()
        data = response.json()
        # Return a list of dictionaries containing dag_id and dag_name
        return [
            {
                "dag_id": dag.get("dag_id", "unknown"),
                "dag_name": dag.get("dag_display_name", "unknown"),
            }
            for dag in data.get("dags", [])
        ]
    except Exception as e:
        print(f"Error fetching DAGs: {e}")
        return []


def fetch_logs_for_dag(dag_id: str) -> dict:
    dag_runs_url = f"{AIRFLOW_URL}/api/v1/dags/{dag_id}/dagRuns"
    try:
        response = requests.get(dag_runs_url, auth=(USERNAME, PASSWORD))
        response.raise_for_status()
        dag_runs = response.json().get("dag_runs", [])

        logs = {}

        for dag_run in dag_runs:
            dag_run_id = dag_run.get("dag_run_id", "unknown")
            task_instances_url = (
                f"{AIRFLOW_URL}/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances"
            )
            task_response = requests.get(task_instances_url, auth=(USERNAME, PASSWORD))
            task_response.raise_for_status()
            task_instances = task_response.json().get("task_instances", [])

            for task in task_instances:
                task_id = task.get("task_id", "unknown")
                task_try_number = task.get(
                    "try_number", 1
                )  # Default to the first try if not specified
                logs_url = f"{AIRFLOW_URL}/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/logs/{task_try_number}"

                # Fetch logs
                log_response = requests.get(logs_url, auth=(USERNAME, PASSWORD))

                # Check if the response is valid JSON
                try:
                    log_response.raise_for_status()
                    if log_response.headers.get("Content-Type") == "application/json":
                        log_data = log_response.json()
                        logs[task_id] = log_data.get("logs", "No logs found.")
                    else:
                        # If not JSON, return the raw text
                        logs[task_id] = log_response.text
                except json.JSONDecodeError as json_err:
                    logs[task_id] = f"Error fetching logs: {json_err}"
                except Exception as e:
                    logs[task_id] = f"Error fetching logs for task {task_id}: {e}"

        return logs  # Return a dictionary of logs keyed by task_id
    except Exception as e:
        print(f"Error fetching logs for DAG {dag_id}: {e}")
        return {}


def save_output_to_json(data: dict, directory: str, filename: str) -> None:
    # Create the directory if it doesn't exist
    os.makedirs(directory, exist_ok=True)
    # Define the full path for the output file
    file_path = os.path.join(directory, filename)
    # Write the data to a JSON file
    with open(file_path, "w") as json_file:
        json.dump(data, json_file, indent=4)
    print(f"Data saved to {file_path}")


# Example usage
if __name__ == "__main__":
    dags = fetch_dags()
    if dags:
        # Example: Fetch logs for a specific DAG ID
        dag_id = dags[0]["dag_id"]  # Get the first DAG ID for demonstration
        logs = fetch_logs_for_dag(dag_id)
        print(f"Logs for DAG ID '{dag_id}':", logs)

        # Save the logs to a JSON file
        save_output_to_json(logs, OUTPUT_DIR, OUTPUT_FILE)
    else:
        print("No DAGs fetched. Exiting.")
