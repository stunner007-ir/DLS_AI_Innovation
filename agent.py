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

    llm = ChatOllama(model="llama3.2", temperature=0)
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


# from dotenv import load_dotenv
# from langchain.agents import initialize_agent, Tool, AgentType
# from langchain_ollama import ChatOllama
# from langchain.prompts import PromptTemplate
# import json
# from logs_fetch.log_actions import fetch_dags, fetch_logs_for_dag  # Importing tools from separate files

# # Load environment variables
# load_dotenv()

# # Define the tools as separate functions

# # Tool for fetching DAGs (defined in logs/log_actions.py or similar)
# def list_dags_tool() -> str:
#     return fetch_dags()

# # Tool for fetching logs for a specific DAG (defined in logs/log_actions.py or similar)
# def fetch_logs_tool(dag_id: str) -> str:
#     return fetch_logs_for_dag(dag_id)

# # List of Tools (can be dynamically loaded)
# tools = [
#     Tool(
#         name="ListDags",
#         func=list_dags_tool,
#         description="Lists all the DAGs from the given endpoint. Useful when the user asks for available DAGs."
#     ),
#     Tool(
#         name="FetchLogs",
#         func=fetch_logs_tool,
#         description="Fetches logs for a specific DAG ID. Useful when the user asks for logs of a particular DAG."
#     )
# ]

# # Define a custom function to handle responses from the agent
# def process_agent_response(response_json: dict) -> str:
#     # Action handler will be done by Langchain agent itself, so we only process its result
#     try:
#         action_type = response_json.get("action", "")
#         argument = response_json.get("argument", "")
        
#         # If no action, return the raw answer
#         if action_type == "answer":
#             return argument
#         else:
#             # Return the appropriate tool result
#             if action_type == "fetch_logs":
#                 return fetch_logs_tool(argument)
#             elif action_type == "list_dags":
#                 return list_dags_tool()
#             else:
#                 return f"Unknown action type: {action_type}"
#     except Exception as e:
#         return f"Error processing response: {str(e)}"

# # Define the Langchain React Agent
# def agent(query: str) -> str:
#     instruction = (
#         "You are an intelligent agent with access to the following tools:\n\n"
#         "1. DAG Listing Tool - To list DAGs from a given endpoint.\n"
#         "   When needed, output in JSON: {\"action\": \"list_dags\", \"argument\": \"\"}\n\n"
#         "2. Log Fetching Tool - To fetch logs from a DAG.\n"
#         "   When needed, output in JSON: {\"action\": \"fetch_logs\", \"argument\": \"<dag_id>\"}\n\n"
#         "3. Answer directly if no tool is necessary.\n"
#         "   Output in JSON: {\"action\": \"answer\", \"argument\": \"<your answer>\"}\n\n"
#         "Ensure that your output is valid JSON. Do not include explanations or extra text."
#     )

#     # Initialize Langchain's LLM
#     llm = ChatOllama(model="llama3.2", temperature=0)

#     # Create a prompt template
#     prompt_template = PromptTemplate(
#         input_variables=["instruction", "query"],
#         template="{instruction}\n\nUser Query: {query}"
#     )

#     # Use Langchain's agent system to automatically select and run the tools
#     agent_executor = initialize_agent(
#         tools, llm, agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION, verbose=True
#     )

#     # Execute the agent
#     response = agent_executor.run(query)
    
#     # Parse the response to ensure valid JSON
#     try:
#         parsed = json.loads(response)
#         return process_agent_response(parsed)
#     except Exception as e:
#         return response

# # Example usage
# if __name__ == "__main__":
#     user_query = "fetch logs details for dag_id example_dag"  # Example user query
#     response = agent(user_query)
#     print("Response:", response)

