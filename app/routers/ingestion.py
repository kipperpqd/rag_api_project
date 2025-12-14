# app/routers/ingestion.py

from fastapi import APIRouter, HTTPException, BackgroundTasks
from tempfile import TemporaryDirectory
from pydantic import BaseModel
from uuid import uuid4
import shutil
import asyncio
import os
import traceback
from typing import List, Dict

# Importações dos Services e Core
from ..services.document_loader import handle_document_load_from_path
from ..services.ocr_processor import refine_extracted_content
from ..services.vector_db_manager import run_ingestion_pipeline
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
    Executa a pipeline completa RAG (download, load, refine, chunk, embed, persist) 
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
        # Chamamos download_drive_file, passando o caminho do diretório temporário
        download_path = await download_drive_file(user_id, file_id, filename, temp_dir) 
        
        if not download_path:
            # Esta mensagem de erro é ativada se download_drive_file retornar None
            print(f"ERRO: Falha no download de {filename}. Caminho inválido ou arquivo não encontrado.")
            return False

        # Etapa 2: Carregamento (O arquivo AGORA existe!)
        print(f"DEBUG: Etapa 2: Carregando documento de {download_path}...")
        document_content = await handle_document_load_from_path(download_path)
        
        # Etapa 3: Refinamento (Plumber/OCR)
        print("DEBUG: Etapa 3: Refinando conteúdo...")
        refined_content = await refine_extracted_content(document_content)
        
        # Etapa 4: Pipeline RAG (Chunking/Embedding/DB)
        print("DEBUG: Etapa 4: Iniciando Pipeline RAG...")
        document_uuid = str(uuid4())
        success = await run_ingestion_pipeline(refined_content, document_uuid, filename)
        
        return success
    
    except Exception as e:
        # Captura qualquer falha subsequente (Carregamento, Refinamento ou DB)
        import traceback
        print(f"ERRO FATAL NA PIPELINE de {filename}: {e}")
        traceback.print_exc()
        return False
        
    finally:
        # Limpeza (CHAMADA EXPLÍCITA: O objeto é limpo AGORA e não quando a função retorna)
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
