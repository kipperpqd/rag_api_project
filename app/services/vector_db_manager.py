# app/services/vector_db_manager.py

from typing import List, Dict, Any, Union, Tuple
from langchain_core.documents import Document # Se você usar Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from ..core.llm_clients import get_embedding_model_client
from ..core.supabase_client import get_supabase_client # Supabase client configurado
from supabase import create_client, Client
import os

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
TABLE_NAME = "documents"
EMBEDDING_MODEL = "text-embedding-ada-002" # Modelo da OpenAI (1536 dimensões)

# Inicialização do Cliente OpenAI (para embeddings)
def get_openai_client():
    # A biblioteca openai geralmente procura pela variável OPENAI_API_KEY
    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("Variável de ambiente OPENAI_API_KEY não definida.")
    return OpenAI()

# Inicializações globais
try:
    supabase: Client = get_supabase_client()
    openai_client: OpenAI = get_openai_client()
    print("INFO: Clientes Supabase e OpenAI inicializados com sucesso.")
except ValueError as e:
    print(f"ERRO DE INICIALIZAÇÃO: {e}")
    supabase = None
    openai_client = None

# Esta função deve ser chamada no início do seu serviço
def get_supabase_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("Variáveis de ambiente SUPABASE_URL ou SUPABASE_KEY não definidas.")
    return create_client(SUPABASE_URL, SUPABASE_KEY)

# Inicialize o cliente:
supabase: Client = get_supabase_client()

# Tipo de dado consolidado que recebemos do ocr_processor.py
ConsolidatedText = List[Dict[str, Union[str, int, str]]] 

# --- Configurações de Chunking (Ajustáveis) ---
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

def create_chunks(refined_content: ConsolidatedText, document_metadata: Dict[str, Any]) -> List[Document]:
    """
    Divide o conteúdo refinado em chunks otimizados para RAG e adiciona metadados.
    
    Args:
        refined_content: Lista de dicionários de texto/descrição por página.
        document_metadata: Metadados globais do documento (ex: nome do arquivo, autor).
        
    Returns:
        Lista de objetos Document do LangChain, prontos para embedding.
    """
    
    # 1. Inicializa o divisor de texto (Text Splitter)
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ".", "!", "?", " "] # Ordem de separação inteligente
    )
    
    all_chunks: List[Document] = []
    
    for item in refined_content:
        # Metadados específicos do chunk (combina global e por página/item)
        metadata = {
            **document_metadata, # nome do arquivo, ID de ingestão, etc.
            "page_number": item["page_number"],
            "content_type": item["content_type"], # TEXT, VISUAL_DESCRIPTION
            "source_loader": item["metadata_source"], # PDFPLUMBER, LLM_MULTIMODAL
        }
        
        # 2. Divide o texto do item
        chunks = text_splitter.create_documents(
            texts=[item["text"]],
            metadatas=[metadata] # O LangChain aplica estes metadados a todos os chunks gerados
        )
        
        all_chunks.extend(chunks)

    print(f"Total de Chunks criados: {len(all_chunks)}")
    return all_chunks


async def generate_embeddings(chunks: List[Document]) -> List[List[float]]:
    """
    Gera os embeddings vetoriais para a lista de chunks de texto.
    
    Args:
        chunks: Lista de objetos Document (LangChain).
        
    Returns:
        Lista de vetores (embeddings), onde cada vetor é uma lista de floats.
    """
    
    # Obtém o cliente do modelo de Embedding
    embedding_client = get_embedding_model_client()
    
    texts_to_embed = [chunk.page_content for chunk in chunks]
    
    print(f"-> Gerando {len(texts_to_embed)} embeddings...")
    
    # Lógica real para chamada à API de Embedding:
    # embeddings = await embedding_client.embed_documents(texts_to_embed)
    
    # Placeholder: Simula a geração de embeddings (ex: 1536 dimensões)
    mock_embedding_dimension = 1536 
    embeddings = [[i] * mock_embedding_dimension for i in range(len(texts_to_embed))]
    
    print("-> Geração de Embeddings concluída.")
    return embeddings

async def insert_chunks_into_db(chunks: List[Document], embeddings: List[List[float]], table_name: str = "documents"):
    """
    Insere os chunks e seus respectivos embeddings no Supabase.
    
    Args:
        chunks: Lista de objetos Document do LangChain.
        embeddings: Lista de vetores numéricos.
        table_name: Nome da tabela de destino no Supabase.
    """
    supabase = get_supabase_client()
    data_to_insert = []
    
    for chunk, embedding in zip(chunks, embeddings):
        # A chave é mapear o objeto Document e o vetor para o esquema da tabela
        data_to_insert.append({
            "content": chunk.page_content, # O texto do chunk
            "embedding": embedding,         # O vetor numérico
            "metadata": chunk.metadata,     # Todos os metadados (página, arquivo, tipo)
            "source_file_id": chunk.metadata.get("document_id") # Para pesquisas futuras
        })

    print(f"-> Inserindo {len(data_to_insert)} registros na tabela '{table_name}'...")

    # Lógica real de inserção no Supabase:
    # response = await supabase.from_(table_name).insert(data_to_insert).execute()
    
    # Placeholder de sucesso
    print("-> Inserção simulada no Supabase bem-sucedida.")
    # return response

# app/services/vector_db_manager.py (Adicione no final)
# ... (após a função insert_chunks_into_db)

async def run_ingestion_pipeline(refined_content: str, document_id: str, original_filename: str) -> bool:
    
    # 1. Definir Metadados
    document_metadata = {
        "id": document_id,
        "filename": original_filename,
        "source": "Google Drive",
    }
    
    print(f"--- INICIANDO PIPELINE DE INGESTÃO para {document_metadata.get('filename')} ---")

    if not supabase or not openai_client:
        print("ERRO: Clientes Supabase ou OpenAI não estão inicializados. Abortando ingestão.")
        return False

    # 2. Chunking (Divisão do texto)
    try:
        # Usa um splitter que respeita caracteres (tokens) para melhor performance em RAG
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
            separators=["\n\n", "\n", " ", ""]
        )
        
        # Divide o conteúdo refinado em chunks
        chunks = text_splitter.split_text(refined_content)
        print(f"Total de Chunks criados: {len(chunks)}")
    except Exception as e:
        print(f"ERRO DE CHUNKING: {e}")
        traceback.print_exc()
        return False

    # 3. Embedding (Geração de Vetores)
    try:
        print(f"-> Gerando {len(chunks)} embeddings...")
        
        # Chamada ao modelo de embedding da OpenAI
        # Nota: Você pode precisar lidar com chamadas em lote (batching) se a lista for muito grande (> 2048 chunks)
        response = openai_client.embeddings.create(
            input=chunks,
            model=EMBEDDING_MODEL
        )
        
        # Extrai os vetores da resposta
        embeddings = [item.embedding for item in response.data]
        print("-> Geração de Embeddings concluída.")
    except Exception as e:
        print(f"ERRO DE EMBEDDING: Falha ao gerar vetores.")
        print(f"Verifique sua OPENAI_API_KEY ou cotas de uso.")
        traceback.print_exc()
        return False

    # 4. Persistência (Inserção no Supabase)
    
    # Monta a lista final de registros no formato do Supabase/pgvector
    records_to_insert = []
    for i, chunk in enumerate(chunks):
        records_to_insert.append({
            "content": chunk,
            "embedding": embeddings[i],
            "document_id": document_id,
            "filename": original_filename,
            # 'metadata' é um campo JSONB no DB
            "metadata": document_metadata
        })

    print(f"-> Inserindo {len(records_to_insert)} registros na tabela '{TABLE_NAME}'...")

    try:
        # Chamada real ao Supabase (usando a Service Key)
        response = (
            supabase
            .table(TABLE_NAME)
            .insert(records_to_insert)
            .execute()
        )

        # Verifica o sucesso
        if response.data or (hasattr(response, 'count') and response.count is not None):
            print(f"-> INSERÇÃO REAL no Supabase bem-sucedida. {len(records_to_insert)} registros adicionados.")
            return True
        else:
            print(f"AVISO: Inserção no Supabase não retornou dados. Verifique a tabela '{TABLE_NAME}'.")
            return False

    except Exception as e:
        print(f"ERRO FATAL DE PERSISTÊNCIA: Falha ao inserir no Supabase.")
        print(f"Detalhes do Erro: {e}")
        traceback.print_exc()
        return False
