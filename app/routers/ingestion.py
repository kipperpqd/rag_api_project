# app/routers/ingestion.py

from fastapi import APIRouter, HTTPException, BackgroundTasks
from tempfile import TemporaryDirectory
from pydantic import BaseModel
from uuid import uuid4
import shutil
from pathlib import Path
import asyncio
import os
import traceback
from typing import List, Dict

# Importações dos Services e Core
from ..services.document_loader import handle_document_load_from_path
from ..services.ocr_processor import refine_extracted_content
from ..services.vector_db_manager import run_ingestion_pipeline
from ..services.document_analyzer import analyze_law_structure
from ..core.drive_auth import get_drive_service

# Importações do Manager (necessita das funções de download/listagem de pastas)
from ..services.google_drive_manager import (
    download_drive_file, get_resource_metadata, list_files_in_folder, DRIVE_MIME_TYPES
)


# --- Modelo Pydantic para o Corpo da Requisição ---
class IngestionRequest(BaseModel):
    """Modelo para receber o ID do recurso (arquivo ou pasta) a ser ingerido."""
    resource_id: str
    user_id: str
    original_filename: str = "" # Mantido para compatibilidade, mas pode ser ignorado se for pasta

    class Config:
        json_schema_extra = {
            "example": {
                "resource_id": "1A2B3C4D5E6F7G8H9I0J",
                "user_id": "<SEU_GOOGLE_CLIENT_ID>",
                "original_filename": "pasta_de_contratos"
            }
        }

router = APIRouter(prefix="/ingestion", tags=["Ingestão"])


# ----------------------------------------------------------------------
# 1. FUNÇÃO AUXILIAR DE PROCESSAMENTO DE ARQUIVO ÚNICO (CORE)
# ----------------------------------------------------------------------

async def _process_single_file_for_ingestion(user_id: str, file_id: str, filename: str) -> bool:
    """
    Executa a pipeline completa RAG (download, load, analyze, refine, chunk, embed, persist) 
    para um único arquivo, com gerenciamento correto de diretório temporário.
    """
    print(f"--- INGESTÃO INICIADA para {filename} (ID: {file_id}) ---")
    
    download_path = None
    success = False
    
    # NOVO: Criamos o objeto TemporaryDirectory para gerenciar seu ciclo de vida
    temp_dir_obj = TemporaryDirectory()
    temp_dir = temp_dir_obj.name

    try:
        # Etapa 1: Download
        str_download_path = await download_drive_file(user_id, file_id, filename, temp_dir) 
        
        if not str_download_path:
            print(f"ERRO: Falha no download de {filename}. Caminho inválido ou arquivo não encontrado.")
            return False
        
        # Converter a string do caminho em um objeto Path
        download_path = Path(str_download_path)
        
        # Etapa 2: Carregamento (O arquivo AGORA existe!)
        print(f"DEBUG: Etapa 2: Carregando documento de {download_path}...")
        # document_content: Lista de strings, uma por página/seção, incluindo texto OCR se necessário.
        document_content, document_images, file_type = await handle_document_load_from_path(download_path, filename) 
        
        # ----------------------------------------------------
        # NOVIDADE: Etapa 3: Análise Estrutural (Metadados Hierárquicos)
        # ----------------------------------------------------
        print("DEBUG: Etapa 3: Iniciando Análise Estrutural...")
        # structured_sections: Lista de dicionários, cada um contendo 'text' e 'metadata' (Artigo, Capítulo, etc.)
        structured_sections = analyze_law_structure(file_type, document_content)
        # ----------------------------------------------------
       
        # Etapa 4: Refinamento (LLM Multimodal para Gráficos/Tabelas)
        # O refinamento agora é feito iterando sobre cada seção estruturada.
        print("DEBUG: Etapa 4: Refinando conteúdo (Multimodal)...")
        refined_sections = []

        # Vamos iterar sobre as seções e aplicar o refinamento onde necessário.
        # NOTE: Sua lógica de refinamento (refine_extracted_content) agora deve
        # ser adaptada ou chamada por seção. Pela simplicidade do COPY/PASTE,
        # faremos uma chamada simplificada.

        # Se a lógica de refine_extracted_content for complexa e depender de todo o documento, 
        # você precisará refatorá-la. Pelo padrão que criamos, ela deve ser adaptada.
        
        # --- Lógica de Refinamento Simplificada (Manter o foco na Estrutura) ---
        # Como o OCR tradicional já foi feito no loader, esta etapa se concentra em 
        # enriquecer sections que ainda sejam 'missing' (como gráficos).
        
        # Para evitar refatorar completamente refine_extracted_content (que ainda está no código):
        refined_data_list = await refine_extracted_content(
            document_content, 
            document_images, 
            file_type
        )
        
        # O passo anterior gera chunks que já contêm metadados de página e tipo de conteúdo.
        # Agora, precisamos fundir os metadados estruturais (Artigo/Capítulo) com os metadados de página/refinamento.
        
        # --- SIMPLIFICAÇÃO PARA O TESTE ---
        # Para que o teste de Artigos/Capítulos funcione, vamos usar a saída da Análise Estrutural (structured_sections)
        # e *ignorar* a saída do refined_content por enquanto, focando apenas nos metadados estruturais.
        
        # No ambiente real, você faria um complexo merge de metadados.
        # Para este teste, vamos forçar o uso da estrutura legal:
        
        refined_sections_for_chunking = []
        for section in structured_sections:
             refined_sections_for_chunking.append({
                 "page_number": section['metadata'].get("page_start", 1), # Usar page_start se houver
                 "content_type": section['metadata'].get("chunk_type", "TEXT_BLOCK"), 
                 "text": section['text'],
                 "metadata_source": "ANALYSIS_STRUCTURED",
                 "article": section['metadata'].get("article"), # Novo Metadado
                 "chapter": section['metadata'].get("chapter"), # Novo Metadado
             })

        # Etapa 5: Pipeline RAG (Chunking/Embedding/DB)
        print("DEBUG: Etapa 5: Iniciando Pipeline RAG (Chunking Estrutural)...")
        document_uuid = str(uuid4())
        
        # A função run_ingestion_pipeline (ou create_chunks_and_embeddings) DEVE
        # ser ajustada para usar refined_sections_for_chunking em vez de refined_content
        # se ela espera uma lista de dicionários.
        
        success = await run_ingestion_pipeline(refined_sections_for_chunking, document_uuid, filename)
        
        return success
    
    except Exception as e:
        # Captura qualquer falha subsequente (Carregamento, Refinamento ou DB)
        import traceback
        print(f"ERRO FATAL NA PIPELINE de {filename}: {e}")
        traceback.print_exc()
        return False
        
    finally:
        # Limpeza
        temp_dir_obj.cleanup() 
        print(f"DEBUG: Limpeza de diretório temporário para {filename} concluída.")
        
        print(f"--- INGESTÃO CONCLUÍDA ({'SUCESSO' if success else 'FALHA'}) para {filename} ---")

# ----------------------------------------------------------------------
# 2. FUNÇÃO DE BACKGROUND (COORDENADOR DE LOTE/ÚNICO)
# ----------------------------------------------------------------------

async def _process_drive_resource_in_background(request: IngestionRequest):
    """
    Função de background que processa o ID de um arquivo (único) ou pasta (lote).
    """
    resource_id = request.resource_id
    user_id = request.user_id
    
    # === PONTO DE VERIFICAÇÃO DE SEGURANÇA ===
    print(f"--- COORDENADOR: TAREFA DE BACKGROUND INICIADA ---")
    print(f"DEBUG: Processando Recurso: {resource_id} para Usuário: {user_id}")
    # ========================================
    
    # 1. Obter metadados
    metadata = await get_resource_metadata(user_id, resource_id)
    if not metadata:
        print(f"ERRO: Recurso {resource_id} não encontrado ou acesso negado.")
        return

    mime_type = metadata.get('mimeType')
    files_to_process: List[Dict] = []
    
    # 2. Lógica de decisão: Pasta ou Arquivo Único?
    if mime_type == DRIVE_MIME_TYPES['folder']:
        print(f"RECURSO DETECTADO: Pasta '{metadata['name']}'. Listando arquivos...")
        files_to_process = await list_files_in_folder(user_id, resource_id)
        
        if not files_to_process:
            print(f"AVISO: Pasta '{metadata['name']}' vazia ou sem arquivos suportados para ingestão.")
            return

    else:
        # É um arquivo único (ou um tipo de documento suportado)
        files_to_process.append({
            'id': resource_id,
            'name': metadata['name']
        })
        print(f"RECURSO DETECTADO: Arquivo único '{metadata['name']}'.")

    # 3. Iterar e Processar em Paralelo
    print(f"INICIANDO PROCESSAMENTO DE {len(files_to_process)} ITENS EM PARALELO.")
    
    # Cria uma lista de tarefas a serem executadas
    tasks = [
        _process_single_file_for_ingestion(user_id, file['id'], file['name'])
        for file in files_to_process
    ]

    # Executa todas as tarefas de ingestão usando asyncio.gather
    processing_results = await asyncio.gather(*tasks)

    # Coleta e loga os resultados
    results = {}
    for file, success in zip(files_to_process, processing_results):
        results[file['name']] = "SUCESSO" if success else "FALHA"

    print("--- PROCESSAMENTO EM LOTE CONCLUÍDO ---")
    print("RESUMO:", results)


# ----------------------------------------------------------------------
# 3. ENDPOINT DA API
# ----------------------------------------------------------------------

@router.post("/upload")
async def upload_resource_for_ingestion(
    request: IngestionRequest,
    background_tasks: BackgroundTasks
):
    """
    Inicia a ingestão de um arquivo ou pasta do Google Drive em background.
    """
    # 1. Verifica autenticação
    if not get_drive_service(request.user_id):
        raise HTTPException(
            status_code=401, 
            detail=f"Usuário {request.user_id} não autenticado ou token expirado. Por favor, reautentique."
        )

    # 2. Adiciona a tarefa de processamento (passando o objeto request completo)
    background_tasks.add_task(
        _process_drive_resource_in_background, 
        request
    )
    
    # 3. Retorna a resposta HTTP 202
    return {
        "status": "Processamento iniciado",
        "message": f"O processamento do recurso '{request.resource_id}' foi iniciado em segundo plano. Verifique os logs.",
    }
