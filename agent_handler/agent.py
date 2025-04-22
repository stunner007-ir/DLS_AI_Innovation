from dotenv import load_dotenv
from langchain.prompts.prompt import PromptTemplate
from langchain_ollama import ChatOllama
import re
import json
from agent_tools.log_actions import fetch_logs_for_dag
from agent_tools.fetch_dag_details import fetch_dag_details
from agent_tools.send_to_slack import send_to_slack
import os
from datetime import datetime


load_dotenv()


class BaseAction:
    def run(self, argument: str) -> str:
        raise NotImplementedError()


class FetchDagDetailsAction(BaseAction):
    def run(self, argument: str) -> str:
        """Fetches details for a specific DAG."""
        dag_name = argument.strip()
        dag_details = fetch_dag_details(dag_name)
        return dag_details


class SaveDagDetailsAction(BaseAction):
    def run(self, argument: str) -> str:
        """Saves the provided DAG details to a JSON file."""
        try:
            data = json.loads(argument)  # Parse the JSON string argument
            dag_name = data.get(
                "dag_name", "default_dag"
            )  # Extract dag_name, provide a default
            filename = f"{dag_name.replace(' ', '_')}_details.json"
            with open(filename, "w") as json_file:
                json.dump(data, json_file, indent=4)
            return f"DAG details saved to {filename}"
        except json.JSONDecodeError:
            return "Error: Invalid JSON provided for saving DAG details."
        except Exception as e:
            return f"Error saving DAG details to JSON: {e}"


class FetchLogsAction(BaseAction):
    def run(self, argument: str) -> str:
        """Fetches logs for a specific DAG."""
        dag_id = argument.strip()
        log_content = fetch_logs_for_dag(dag_id)
        return log_content


class AnalyzeLogsAction(BaseAction):
    def run(self, argument: str) -> str:
        """Analyzes the provided logs and returns the analysis."""
        log_content = argument

        # Analyze the logs
        analysis_prompt = f"""
        Analyze the following Airflow DAG logs and identify the root cause of any failures or errors.
        Provide a concise summary of the issue and potential solutions.

        Logs:
        {log_content}
        """

        llm = ChatOllama(model="llama3.2", temperature=0.4)
        analysis_result = llm.invoke(analysis_prompt).content

        return analysis_result


class AnswerAction(BaseAction):
    def run(self, argument: str) -> str:
        return argument


class SendToSlackAction(BaseAction):
    def run(self, argument: str) -> str:
        """Sends a message to Slack using the send_to_slack tool."""
        return send_to_slack(argument)


ACTION_REGISTRY = {
    "fetch_dag_details": FetchDagDetailsAction(),
    "fetch_logs": FetchLogsAction(),
    "analyze_logs": AnalyzeLogsAction(),
    "answer": AnswerAction(),
    "send_to_slack": SendToSlackAction(),
    "save_dag_details": SaveDagDetailsAction(),
}


def dispatch_action(response_json: dict) -> str:
    action_type = response_json.get("action", "answer")
    argument = response_json.get("argument", "")
    action_handler = ACTION_REGISTRY.get(action_type, AnswerAction())
    return action_handler.run(argument)


def agent(query: str) -> str:
    instruction = """
You are an intelligent assistant that can monitor, analyze, and troubleshoot Apache Airflow DAGs.

You have access to the following tools and **must respond using one of the defined JSON formats below**.

---

**TOOLS YOU CAN USE:**

1. **DAG Details Fetching Tool**
   - Purpose: Fetch details for a specific DAG.
   - Input: The DAG name, ID, or display name.
   - Output Format:
     ```json
     {"action": "fetch_dag_details", "argument": "<dag_name_or_id>"}
     ```

2. **Save DAG Details Tool**
   - Purpose: Save the fetched DAG details to a JSON file.
   - Input: The DAG details as a JSON string. Must include a `"dag_name"` key.
   - Output Format:
     ```json
     {"action": "save_dag_details", "argument": "<dag_details_json_string>"}
     ```

3. **Log Fetching Tool**
   - Purpose: Fetch logs for a DAG.
   - Input: DAG name or ID.
   - Output Format:
     ```json
     {"action": "fetch_logs", "argument": "<dag_name_or_id>"}
     ```

4. **Log Analysis Tool**
   - Purpose: Analyze DAG logs to find issues and suggest solutions.
   - Input: Raw log content as a string.
   - Output Format:
     ```json
     {"action": "analyze_logs", "argument": "<log_content_string>"}
     ```

5. **Slack Notification Tool**
   - Purpose: Notify a Slack channel about DAG issues.
   - Input: A summary message including the DAG name and issue.
   - Output Format:
     ```json
     {"action": "send_to_slack", "argument": "<summary_message_with_dag_name>"}
     ```

6. **Answer Tool**
   - Purpose: Reply directly without calling a tool.
   - Output Format:
     ```json
     {"action": "answer", "argument": "<direct_response>"}
     ```

---

**IMPORTANT LOGIC TO FOLLOW:**

- If analyzing a DAG failure:
  1. Use `fetch_logs`
  2. Then `analyze_logs`
  3. Then `send_to_slack` with the analysis and DAG name

Always return **valid JSON only**. Do **not** include explanations, commentary, or extra text outside the JSON object.
"""

    prompt_template = PromptTemplate(
        input_variables=["instruction", "query"],
        template="{instruction}\n\nUser Query: {query}",
    )

    llm = ChatOllama(model="llama3.2", temperature=0.6)
    chain = prompt_template | llm
    response = chain.invoke(input={"instruction": instruction, "query": query})
    content = response.content if hasattr(response, "content") else response
    content = content.strip()

    try:
        parsed = json.loads(content)
        return dispatch_action(parsed)

    except Exception as e:
        return content
