from dotenv import load_dotenv
import os
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import chain
from langchain_core.tools import Tool
import re
import requests
import json
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from typing import TypedDict, List, Dict, Any

# Airflow URL and credentials
AIRFLOW_URL = "http://localhost:8080"
USERNAME = "airflow"
PASSWORD = "airflow"


# --- Tool Definitions ---

def evaluate_expression(expression: str) -> str:
    """Evaluates a mathematical expression."""
    if not re.match(r'^[\d+\-*/.\s()]+$', expression):
        return "Error: Invalid characters in expression."
    try:
        result = eval(expression, {"__builtins__": None}, {})
        return f"{expression} = {result}"
    except Exception as e:
        return f"Error in calculation: {e}"


def fetch_dags() -> str:
    """Fetches a list of DAGs from Airflow."""
    url = f"{AIRFLOW_URL}/api/v1/dags"
    try:
        response = requests.get(url, auth=(USERNAME, PASSWORD))
        response.raise_for_status()
        data = response.json()
        dag_list = []
        if "dags" in data:
            for dag in data["dags"]:
                dag_list.append(dag.get("dag_id", "unknown"))
            return "DAGs: " + ", ".join(dag_list)
        return str(data)
    except Exception as e:
        return f"Error fetching DAGs: {e}"


calculate_tool = Tool(
    name="Calculator",
    func=evaluate_expression,
    description="Use this tool ONLY to evaluate arithmetic expressions. Input MUST be a valid mathematical expression."
)


list_dags_tool = Tool(
    name="ListDAGs",
    func=fetch_dags,
    description="Use this tool ONLY when the user explicitly asks to list DAGs from Airflow. Do not pass any input to this tool."
)


tools = [calculate_tool, list_dags_tool]


# --- LLM and Prompt ---

llm = ChatOllama(model="llama3.2", temperature=0)
model_with_tools = llm.bind_tools(tools)


prompt = ChatPromptTemplate.from_messages([
    ("system", """You are an intelligent agent designed to assist users. You can use tools to answer questions.
             You have access to the following tools:

{tool_descriptions}

             When answering, you MUST follow this format:

             ```
             Question: the input question you must answer
             Thought: you should always think about what to do
             Action: the action to take, should be one of: [{tool_names}]
             Action Input: the input to the action
             Observation: the result of the action
             ... (this Thought/Action/Action Input/Observation can repeat N times)
             Thought: I am ready to answer
             Final Answer: the final answer to the original input question
             ```

             Begin!
"""),
    MessagesPlaceholder(variable_name="messages"),
])


tool_descriptions = "\n".join([f"{tool.name}: {tool.description}" for tool in tools])
tool_names = ", ".join([tool.name for tool in tools])


prompt = prompt.partial(
    tool_names=tool_names,
    tool_descriptions=tool_descriptions,
)


# --- Agent State ---

class AgentState(TypedDict):
    messages: List[HumanMessage | AIMessage | ToolMessage]
    intermediate_response: Any  # Add this to store the intermediate response


# --- Nodes ---

def agent(state: AgentState):
    messages = state["messages"]
    prompt_value = prompt.invoke({"messages": messages})  # Get ChatPromptValue
    response = model_with_tools.invoke(prompt_value)  # Pass to LLM
    return {"messages": [*messages, response], "intermediate_response": response}  # Store LLM's response


def call_tool(state: AgentState):
    messages = state["messages"]
    last_message = state["intermediate_response"]  # Use the stored intermediate response
    tool_calls = last_message.tool_calls
    tool_name = tool_calls[0].function.name
    tool = next((tool for tool in tools if tool.name == tool_name), None)
    if tool is None:
        raise ValueError(f"No tool found with name {tool_name}")
    tool_input = tool_calls[0].function.arguments
    # Parse the tool input string to a dictionary
    try:
        tool_input_dict = json.loads(tool_input)
    except json.JSONDecodeError:
        tool_input_dict = {"expression": tool_input}  # Default to expression if parsing fails
    tool_output = tool.func(**tool_input_dict)  # Call the tool's function with keyword arguments
    return {"messages": [*messages, ToolMessage(content=str(tool_output), name=tool_name, tool_call_id=tool_calls[0].id)], "intermediate_response": None}


def decide_if_finished(state: AgentState):
    messages = state["messages"]
    last_message = state["intermediate_response"]  # Use the stored intermediate response
    if last_message is None or not hasattr(last_message, 'tool_calls') or not last_message.tool_calls:
        return "END"
    else:
        return "call_tool"


# --- Graph Definition ---

graph = StateGraph(AgentState)
graph.add_node("agent", agent)
graph.add_node("call_tool", call_tool)
graph.set_entry_point("agent")  # Add this line to set the entry point
graph.add_conditional_edges(
    "agent",
    decide_if_finished,
    {
        "END": END,
        "call_tool": "call_tool",
    },
)
graph.add_edge("call_tool", "agent")


# --- Memory ---

memory = MemorySaver()
chain = graph.compile()


# --- Agent Response Function ---

def agent_response(query: str, thread_id: str) -> str:
    try:
        inputs = {"messages": [HumanMessage(content=query)], "intermediate_response": None}  # Initialize intermediate_response
        config = {"configurable": {"thread_id": thread_id}}
        final_response = "I don't know."  # Default response
        for output in chain.stream(inputs, config):
            if "messages" in output:
                messages = output["messages"]
                for message in messages:
                    if isinstance(message, AIMessage) and "Final Answer:" in message.content:
                        final_response = message.content.split("Final Answer:")[-1].strip()
                        break  # Stop searching after finding the final answer
        return final_response
    except Exception as e:
        return f"The agent encountered an error: {e}"


# --- Main Execution ---

if __name__ == "__main__":
    load_dotenv()
    print("Agent ready. Type a query or 'exit' to quit:")
    thread_id = "default_thread"  # You can change this for different conversations

    while True:
        try:
            user_query = input(">> ")
            if user_query.strip().lower() in {"exit", "quit"}:
                print("Stopping agent.")
                break
            output = agent_response(user_query, thread_id)
            print("Response:", output)
        except Exception as e:
            print(f"An error occurred: {e}")