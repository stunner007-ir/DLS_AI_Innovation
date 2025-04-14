from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# This should import the actual logic
from agent import agent

handle_query = APIRouter()

class QueryRequest(BaseModel):
    query: str

@handle_query.post("/")
async def query_agent(request: QueryRequest):
    try:
        response = agent(request.query)
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
