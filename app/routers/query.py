# app/routers/query.py

from fastapi import APIRouter
from pydantic import BaseModel
from ..services.query_manager import run_query_pipeline

router = APIRouter()

class QueryRequest(BaseModel):
    query: str

@router.post("/query")
async def process_query(request: QueryRequest):
    """
    Processa a pergunta do usuário usando a pipeline RAG.
    """
    try:
        response = await run_query_pipeline(request.query)
        
        return {
            "query": request.query,
            "response": response,
            "success": True,
        }
    except Exception as e:
        return {
            "query": request.query,
            "response": f"Erro interno ao processar a requisição: {e}",
            "success": False,
        }
