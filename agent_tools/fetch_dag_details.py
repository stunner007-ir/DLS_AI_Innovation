from dotenv import load_dotenv
import requests
import json
import os
from typing import Dict, Optional, List, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

AIRFLOW_URL = "http://localhost:8080"
USERNAME = "airflow"
PASSWORD = "airflow"

def fetch_dag_details(dag_name: str) -> Optional[Dict[str, Any]]:
    """
    Fetches detailed information about a specific DAG from Airflow.

    Args:
        dag_name (str): The display name of the DAG to fetch.

    Returns:
        Optional[Dict[str, Any]]: A dictionary containing the DAG details, or None if the DAG is not found or an error occurs.
    """
    url = f"{AIRFLOW_URL}/api/v1/dags"

    try:
        response = requests.get(url, auth=(USERNAME, PASSWORD))
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        dags: List[Dict[str, Any]] = response.json().get("dags", [])

        # Find the specified DAG
        dag_info: Optional[Dict[str, Any]] = next((dag for dag in dags if dag.get("dag_display_name") == dag_name), None)

        if not dag_info:
            print(f"DAG with name '{dag_name}' not found.")
            return None

        dag_id: str = dag_info.get("dag_id", "unknown")
        dag_description: str = dag_info.get("description", "No description available.")
        dag_schedule_interval: str = dag_info.get("schedule_interval", "No schedule defined.")
        dag_is_active: bool = dag_info.get("is_active", True)
        dag_last_updated: str = dag_info.get("last_updated", "Unknown")

        # Fetching the latest DAG runs for additional details
        dag_runs_url = f"{AIRFLOW_URL}/api/v1/dags/{dag_id}/dagRuns"
        dag_runs_response = requests.get(dag_runs_url, auth=(USERNAME, PASSWORD))
        dag_runs_response.raise_for_status()
        dag_runs: List[Dict[str, Any]] = dag_runs_response.json().get("dag_runs", [])

        # Collecting run details
        run_details: List[Dict[str, Any]] = []
        for run in dag_runs:
            run_id: str = run.get("dag_run_id", "unknown")
            execution_date: str = run.get("execution_date", "unknown")
            run_date: str = run.get("start_date", "unknown")  # Assuming start_date is the run date
            state: str = run.get("state", "unknown")

            # Fetching task instances for the current run
            task_instances_url = f"{AIRFLOW_URL}/api/v1/dags/{dag_id}/dagRuns/{run_id}/taskInstances"
            task_instances_response = requests.get(task_instances_url, auth=(USERNAME, PASSWORD))
            task_instances_response.raise_for_status()
            task_instances: List[Dict[str, Any]] = task_instances_response.json().get("task_instances", [])

            # Collecting task instance details
            task_details: List[Dict[str, Any]] = []
            for task in task_instances:
                task_id: str = task.get("task_id", "unknown")
                task_state: str = task.get("state", "unknown")
                task_try_number: int = task.get("try_number", 1)  # Default to the first try if not specified
                task_start_date: str = task.get("start_date", "unknown")
                task_end_date: str = task.get("end_date", "unknown")

                task_info: Dict[str, Any] = {
                    "task_id": task_id,
                    "state": task_state,
                    "try_number": task_try_number,
                    "start_date": task_start_date,
                    "end_date": task_end_date,
                }
                task_details.append(task_info)

            # Collecting run details including task instances
            run_info: Dict[str, Any] = {
                "run_id": run_id,
                "execution_date": execution_date,
                "run_date": run_date,
                "state": state,
                "tasks": task_details,  # Adding task details to the run info
            }
            run_details.append(run_info)

        # Collecting detailed information for the specified DAG
        detailed_dag_info: Dict[str, Any] = {
            "dag_id": dag_id,
            "dag_name": dag_name,
            "description": dag_description,
            "schedule_interval": dag_schedule_interval,
            "is_active": dag_is_active,
            "last_updated": dag_last_updated,
            "runs": run_details,  # Adding run details to the DAG info
        }

        return detailed_dag_info

    except requests.exceptions.RequestException as e:
        print(f"Error fetching DAG details: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON response: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None
        return {}

# Example usage
if __name__ == "__main__":
    dag_name = "modern_slack_notification_dag"  # Replace with the actual DAG name you want to fetch
    dag_details = fetch_dag_details(dag_name)
    if dag_details:
        print(json.dumps(dag_details, indent=2))
    else:
        print("Failed to fetch DAG details.")
