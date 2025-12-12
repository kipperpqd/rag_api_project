# app/core/supabase_client.py
from supabase import create_client, Client
from .config import settings
from typing import Optional

# Variável global para armazenar a instância do cliente Supabase
_supabase_client: Optional[Client] = None

def initialize_supabase_client() -> Client:
    """
    Inicializa o cliente Supabase usando a URL e a Service Key do .env.
    
    A Service Key (service_role key) é usada aqui para operações de backend 
    de alta permissão (como inserção de embeddings, que ignora as RLS - Row 
    Level Security).
    """
    global _supabase_client
    
    if _supabase_client is None:
        try:
            # 1. Obter as credenciais
            url: str = settings.SUPABASE_URL
            key: str = settings.SUPABASE_SERVICE_KEY
            
            if not url or not key:
                raise ValueError("SUPABASE_URL e SUPABASE_SERVICE_KEY devem ser configurados no .env")

            # 2. Criar e armazenar o cliente (Singleton)
            # O cliente Supabase é thread-safe para operações de I/O
            _supabase_client = create_client(url, key)
            print("INFO: Cliente Supabase inicializado com sucesso.")
            
        except Exception as e:
            print(f"ERRO CRÍTICO ao inicializar o cliente Supabase: {e}")
            raise RuntimeError("Falha na inicialização do cliente Supabase.") from e
            
    return _supabase_client

def get_supabase_client() -> Client:
    """
    Função de conveniência para obter a instância do cliente Supabase já inicializada.
    Esta função será chamada por vector_db_manager.py e chat.py.
    """
    # Garante que o cliente esteja inicializado antes de retornar
    if _supabase_client is None:
        return initialize_supabase_client()
    return _supabase_client

# Exemplo de como você poderia usar o cliente para uma função de busca de vetores
async def search_vectors(embedding_vector: list[float], similarity_threshold: float = 0.75, top_k: int = 5) -> list[Dict]:
    """
    Função de busca (RPC) no banco de dados vetorial PostgreSQL (pgvector).
    Esta função será chamada pelo app/routers/chat.py.
    """
    client = get_supabase_client()
    
    # 1. Nome da função PostgreSQL Rpc (Remote Procedure Call)
    # A função 'match_documents' precisa ser criada no seu Supabase!
    rpc_function_name = "match_documents" 
    
    # 2. Parâmetros passados para a função RPC no banco de dados
    params = {
        'query_embedding': embedding_vector,
        'match_threshold': similarity_threshold,
        'match_count': top_k,
    }

    try:
        # A chamada RPC é usada para executar lógica de busca vetorial no lado do DB
        # data, count = client.rpc(rpc_function_name, params).execute()
        
        # Simulação da Busca
        print(f"-> Mock Search: Buscando {top_k} documentos similares no Supabase...")
        return [
            {"content": "Resultado mock 1", "similarity": 0.9},
            {"content": "Resultado mock 2", "similarity": 0.85},
        ]
    
    except Exception as e:
        print(f"ERRO na busca vetorial Supabase: {e}")
        return []
