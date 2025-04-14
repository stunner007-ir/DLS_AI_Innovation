from dotenv import load_dotenv
from langchain.prompts.prompt import PromptTemplate
from langchain_ollama import ChatOllama
import re
import json
from logs_fetch.log_actions import fetch_dags, fetch_logs_for_dag  # Import log actions

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
        # Extract the dag_id from the argument
        dag_id = argument.strip()
        return fetch_logs_for_dag(dag_id)

class AnswerAction(BaseAction):
    def run(self, argument: str) -> str:
        return argument

ACTION_REGISTRY = {
    "list_dags": ListDagsAction(),
    "fetch_logs": FetchLogsAction(),
    "answer": AnswerAction()
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
        "3. Answer directly if no tool is necessary.\n"
        "   Output in JSON: {\"action\": \"answer\", \"argument\": \"<your answer>\"}\n\n"
        "Ensure that your output is valid JSON. Do not include explanations or extra text."
    )

    prompt_template = PromptTemplate(
        input_variables=["instruction", "query"],
        template="{instruction}\n\nUser Query: {query}"
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

# Example usage
if __name__ == "__main__":
    user_query = "fetch logs details for dag_id example_dag"  # Example user query
    response = agent(user_query)
    print("Response:", response)

