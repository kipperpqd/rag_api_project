# app/main.py
from fastapi import FastAPI
from .routers import ingestion
from .routers import auth # Importação do novo Router
from .routers import query
# Você incluirá o router 'chat' aqui futuramente:
# from .routers import chat 

app = FastAPI(
    title="RAG Product API - Document Ingestion",
    version="1.0.0",
    description="API para ingestão e processamento multimodal de documentos para RAG."
)

# 1. Incluir o Router de Ingestão
app.include_router(ingestion.router)

# 2. Incluir o Router de Autenticação (NOVO)
app.include_router(auth.router)

# 3. Incluir o Router de perguntas (NOVO)
app.include_router(query.router)

# 3. Incluir o Router de Chat (futuro)
# app.include_router(chat.router)


# 3. Rota de Health Check (Verificação de Status)
@app.get("/", tags=["Status"])
def read_root():
    """Verifica se a API está de pé."""
    return {"message": "RAG Ingestion API está operacional!"}

# ROTAS DE TESTE (Opcional, se você quiser manter o /ping)
@app.get("/ping", tags=["Health Check"])
def ping():
    return {"status": "ok", "service": "rag_api"}
