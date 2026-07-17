"""
app.py
======
Local FastAPI server to expose RAG pipeline via HTTP REST API.
"""

from __future__ import annotations

import sys
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent.parent))

from query_pipeline import RAGPipeline

app = FastAPI(
    title="West Tripura District RAG API",
    description="HTTP API for answering citizen questions using Pinecone and NVIDIA Models",
    version="1.0.0"
)

# Initialize pipeline once on startup
try:
    pipeline = RAGPipeline()
except Exception as e:
    print(f"✗ Failed to initialize RAG pipeline: {e}")
    sys.exit(1)


class QueryRequest(BaseModel):
    query: str


class ReferenceItem(BaseModel):
    title: str
    url: str
    section: str


class QueryResponse(BaseModel):
    answer: str
    references: list[ReferenceItem]


@app.get("/")
@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "message": "West Tripura District RAG API is healthy and active."}


@app.post("/query", response_model=QueryResponse)
def query_endpoint(payload: QueryRequest):
    """
    RAG Query answering endpoint.
    Receives JSON: {"query": "some question"}
    Returns generated answer and sources.
    """
    user_query = payload.query.strip()
    if not user_query:
        raise HTTPException(status_code=400, detail="Query string cannot be empty")
        
    try:
        result = pipeline.answer(user_query)
        return QueryResponse(
            answer=result["answer"],
            references=[
                ReferenceItem(
                    title=ref["title"],
                    url=ref["url"],
                    section=ref["section"]
                ) for ref in result["references"]
            ]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Query Error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
