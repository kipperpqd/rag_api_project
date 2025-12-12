# app/services/vector_db_manager.py

from typing import List, Dict, Any, Union, Tuple
from langchain_core.documents import Document # Se você usar Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from ..core.llm_clients import get_embedding_model_client
from ..core.supabase_client import get_supabase_client # Supabase client configurado

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

async def run_ingestion_pipeline(refined_content: ConsolidatedText, document_metadata: Dict[str, Any]):
    """
    Função principal que orquestra a pipeline de ingestão RAG.
    
    1. Cria chunks a partir do conteúdo refinado.
    2. Gera embeddings para cada chunk.
    3. Insere os chunks e embeddings no Supabase.
    """
    print(f"--- INICIANDO PIPELINE DE INGESTÃO para {document_metadata.get('filename')} ---")
    
    # 1. Criação de Chunks
    chunks = create_chunks(refined_content, document_metadata)
    
    if not chunks:
        print("AVISO: Nenhum chunk foi criado. Ingestão cancelada.")
        return False
        
    # 2. Geração de Embeddings
    embeddings = await generate_embeddings(chunks)
    
    # 3. Inserção no Banco de Dados
    await insert_chunks_into_db(
        chunks=chunks,
        embeddings=embeddings,
        table_name=document_metadata.get("supabase_table_name", "documents") # Tabela padrão
    )
    
    print(f"--- PIPELINE CONCLUÍDA: {len(chunks)} chunks ingeridos. ---")
    return True
