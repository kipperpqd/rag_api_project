# app/services/vector_db_manager.py

from typing import List, Dict, Any, Union, Tuple
from ..core.llm_clients import get_embedding_model_client
from ..core.supabase_client import get_supabase_client # Supabase client configurado
import os
import json
import traceback
# Dependências para Chunking e Embedding
from openai import OpenAI # Ou o cliente Gemini, se estiver usando Google GenAI
from langchain_core.documents import Document # Se você usar Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from supabase import create_client, Client

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

async def run_ingestion_pipeline(sections: List[Dict[str, Any]], document_id: str, original_filename: str) -> bool:
    """
    Executa o Chunking Estrutural, Embedding e Persistência no Supabase.
    
    A entrada 'sections' agora é uma lista de dicionários, onde cada item
    contém o 'text' (ex: um Artigo inteiro) e os 'metadata' estruturais.
    
    :param sections: Lista de seções estruturadas (Artigos/Capítulos) com metadados.
    """
    
    # 1. Definir Metadados Base (Metadados que são os mesmos para todos os chunks)
    document_metadata_base = {
        "id": document_id,
        "filename": original_filename,
        "source": "Google Drive",
    }
    
    print(f"--- INICIANDO PIPELINE DE INGESTÃO para {document_metadata_base.get('filename')} ---")

    if not supabase or not openai_client:
        print("ERRO: Clientes Supabase ou OpenAI não estão inicializados. Abortando ingestão.")
        return False

    # 2. Chunking Estrutural (Herança de Metadados)
    all_final_chunks = []
    
    # Função auxiliar para dividir o texto (usada se uma seção for muito longa)
    # Mantemos uma função simples, pois a quebra principal já é por seção
    def simple_text_splitter(text: str, max_len: int = 750) -> List[str]:
        # Usamos uma quebra simples, pois a quebra semântica já foi feita pelo analisador de Artigos
        return [text[i:i + max_len] for i in range(0, len(text), max_len)]

    try:
        # Itera sobre CADA SEÇÃO ESTRUTURAL (Artigo, Capítulo, Preâmbulo)
        for section in sections:
            
            section_text = section['text']
            # Metadados herdados do analisador estrutural (Artigo, Capítulo, etc.)
            inherited_metadata = section['metadata'] 
            
            # Divide o texto da seção em sub-chunks (se o Artigo for muito longo)
            sub_chunks = simple_text_splitter(section_text)
            
            # Anexa os metadados herdados a cada sub-chunk
            for i, chunk_text in enumerate(sub_chunks):
                
                # Combina metadados globais (document_id) com metadados estruturais (article, chapter)
                final_metadata = document_metadata_base.copy()
                
                # Adiciona metadados de controle de posição
                final_metadata.update({
                    "chunk_index": i,  
                    "total_chunks_in_section": len(sub_chunks),
                })
                
                # IMPORTANTE: HERDA OS METADADOS ESTRUTURAIS
                final_metadata.update({
                    "article": inherited_metadata.get('article', 'N/A'),
                    "chapter": inherited_metadata.get('chapter', 'N/A'),
                    "content_type": inherited_metadata.get('content_type', 'TEXT'),
                    "page_number": inherited_metadata.get('page_number', 'N/A'),
                })
                
                all_final_chunks.append({
                    "content": chunk_text,
                    "metadata": final_metadata # Dicionário de metadados completo
                })
                
        print(f"Total de Chunks criados (pós-estrutural): {len(all_final_chunks)}")
        
    except Exception as e:
        print(f"ERRO DE CHUNKING ESTRUTURAL: {e}")
        traceback.print_exc()
        return False

    # 3. Embedding (Geração de Vetores)
    chunk_contents = [c['content'] for c in all_final_chunks]
    
    try:
        print(f"-> Gerando {len(chunk_contents)} embeddings...")
        
        # Chamada ao modelo de embedding da OpenAI
        response = openai_client.embeddings.create(
            input=chunk_contents,
            model=EMBEDDING_MODEL
        )
        
        embeddings = [item.embedding for item in response.data]
        print("-> Geração de Embeddings concluída.")
        
    except Exception as e:
        print(f"ERRO DE EMBEDDING: Falha ao gerar vetores.")
        traceback.print_exc()
        return False

    # 4. Persistência (Inserção no Supabase)
    records_to_insert = []
    
    for i, chunk_data in enumerate(all_final_chunks):
        # O metadado já está completo no chunk_data['metadata']
        
        # NOTE: O Supabase/pgvector requer que a coluna 'embedding' seja um array
        # e a coluna 'metadata' seja um objeto JSONB.
        
        records_to_insert.append({
            "content": chunk_data['content'],
            "embedding": embeddings[i],
            "document_id": document_id,
            "filename": original_filename,
            # CRUCIAL: O campo 'metadata' JSONB recebe o dicionário COMPLETO
            "metadata": chunk_data['metadata'] 
        })

    print(f"-> Inserindo {len(records_to_insert)} registros na tabela '{TABLE_NAME}'...")

    try:
        # [...] (Sua lógica de inserção no Supabase com try/except) [...]
        response = (
            supabase
            .table(TABLE_NAME)
            .insert(records_to_insert)
            .execute()
        )
        
        if response.data or (hasattr(response, 'count') and response.count is not None):
            print(f"-> INSERÇÃO REAL no Supabase bem-sucedida. {len(records_to_insert)} registros adicionados.")
            return True
        else:
            print(f"AVISO: Inserção no Supabase não retornou dados. Verifique a tabela '{TABLE_NAME}'.")
            return False

    except Exception as e:
        print(f"ERRO FATAL DE PERSISTÊNCIA: Falha ao inserir no Supabase.")
        traceback.print_exc()
        return False
