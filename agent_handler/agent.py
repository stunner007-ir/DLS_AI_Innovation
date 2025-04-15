from dotenv import load_dotenv
from langchain.prompts.prompt import PromptTemplate
from langchain_ollama import ChatOllama
import re
import json
from agent_tools.log_actions import fetch_dags, fetch_logs_for_dag
from agent_tools.send_to_slack import send_to_slack
import os
from datetime import datetime


# Load environment variables
load_dotenv()


class BaseAction:
    def run(self, argument: str) -> str:
        raise NotImplementedError()


class ListDagsAction(BaseAction):
    def run(self, argument: str) -> str:
        return fetch_dags()


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
    "list_dags": ListDagsAction(),
    "fetch_logs": FetchLogsAction(),
    "analyze_logs": AnalyzeLogsAction(),
    "answer": AnswerAction(),
    "send_to_slack": SendToSlackAction(),
}


def dispatch_action(response_json: dict) -> str:
    action_type = response_json.get("action", "answer")
    argument = response_json.get("argument", "")
    action_handler = ACTION_REGISTRY.get(action_type, AnswerAction())
    return action_handler.run(argument)


def agent(query: str) -> str:
    instruction = (
        "You are an intelligent agent with access to the following tools:\n\n"
        "1. DAG Listing Tool - To list DAGs from a given endpoint.\n"
        "   When needed, output in JSON: {\"action\": \"list_dags\", \"argument\": \"\"}\n\n"
        "2. Log Fetching Tool - To fetch logs from a DAG.\n"
        "   When needed, output in JSON: {\"action\": \"fetch_logs\", \"argument\": \"<dag_id>\"}\n\n"
        "3. Log Analysis Tool - To analyze logs and provide insights.\n"
        "   When needed, output in JSON: {\"action\": \"analyze_logs\", \"argument\": \"<log_content>\"}\n\n"
        "4. Slack Notification Tool - To send messages to a Slack channel. Also give the Name of the Dag which has error\n"
        "   When needed, output in JSON: {\"action\": \"send_to_slack\", \"argument\": \"<message>\"}\n\n"
        "3. Answer directly if no tool is necessary.\n"
        "   Output in JSON: {\"action\": \"answer\", \"argument\": \"<your answer>\"}\n\n"
        "Ensure that your output is valid JSON. Do not include explanations or extra text."
    )

    prompt_template = PromptTemplate(
        input_variables=["instruction", "query"],
        template="{instruction}\n\nUser Query: {query}",
    )

    llm = ChatOllama(model="llama3.2", temperature=0.4)
    chain = prompt_template | llm
    response = chain.invoke(input={"instruction": instruction, "query": query})
    content = response.content if hasattr(response, "content") else response
    content = content.strip()

    try:
        parsed = json.loads(content)
        return dispatch_action(parsed)

    except Exception as e:
        return content
