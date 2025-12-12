# app/routers/ingestion.py
from fastapi import APIRouter, File, UploadFile, HTTPException, BackgroundTasks
from uuid import uuid4
import os
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from googleapiclient.http import MediaIoBaseDownload
from typing import Optional

# Importações dos Services e Core
from ..services.document_loader import handle_document_load_from_path # Funçao precisa ser adaptada para PATH
from ..services.ocr_processor import refine_extracted_content
from ..services.vector_db_manager import run_ingestion_pipeline
from ..core.drive_auth import get_drive_service # Cliente do Google Drive

router = APIRouter(
    prefix="/rag/ingest",
    tags=["Ingestão de Documentos"],
)

# ----------------------------------------------------------------------
# 1. FUNÇÃO AUXILIAR DE DOWNLOAD
# ----------------------------------------------------------------------

async def download_file_from_drive(service, file_id: str, filename: str, temp_dir: Path) -> Path:
    """Faz o download de um arquivo do Google Drive para um caminho temporário."""
    
    request = service.files().get_media(fileId=file_id)
    temp_file_path = temp_dir / filename
    
    # Usa um buffer de IO para o download
    fh = io.FileIO(temp_file_path, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    
    # Loop de download (executado de forma síncrona dentro da tarefa assíncrona)
    while done is False:
        status, done = downloader.next_chunk()
        # O print abaixo é opcional e pode ser removido em produção
        # print(f"Download {int(status.progress() * 100)}% de {filename}.") 
            
    return temp_file_path


# ----------------------------------------------------------------------
# 2. FUNÇÃO PRINCIPAL DE PROCESSAMENTO EM BACKGROUND
# ----------------------------------------------------------------------

async def _process_drive_file_in_background(user_id: str, file_id: str, original_filename: str):
    """
    Função wrapper que executa o pipeline de ingestão completo para um arquivo do Drive.
    """
    document_id = str(uuid4())
    print(f"\n--- INGESTÃO INICIADA para {original_filename} (ID: {document_id}) ---")

    drive_service = get_drive_service(user_id)
    if not drive_service:
        print(f"ERRO: Serviço do Drive indisponível para o usuário {user_id}. Reautenticação necessária.")
        # Lógica de notificação ao usuário sobre a falha de autenticação
        return

    # Usamos TemporaryDirectory para garantir que o arquivo temporário seja excluído no final
    with TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        temp_file_path: Optional[Path] = None

        try:
            # 1. DOWNLOAD (do Drive para o disco temporário)
            temp_file_path = await download_file_from_drive(
                drive_service, 
                file_id, 
                original_filename, 
                temp_dir
            )
            
            # 2. CARREGAMENTO (app/services/document_loader.py)
            # Adapte 'handle_document_load_from_path' em document_loader para usar Path
            document_text, document_images, file_type = await handle_document_load_from_path(
                temp_file_path, 
                original_filename
            )
            
            # 3. REFINAMENTO (app/services/ocr_processor.py)
            refined_content = await refine_extracted_content(
                document_text, 
                document_images, 
                file_type
            )
            
            # 4. PIPELINE FINAL (app/services/vector_db_manager.py)
            success = await run_ingestion_pipeline(
                refined_content, 
                document_id, 
                original_filename
            )
            
            if not success:
                raise Exception("A inserção final no banco de dados falhou.")
                
        except Exception as e:
            print(f"ERRO DE INGESTÃO CRÍTICO no arquivo {original_filename}: {e}")
            # Lógica de logging/notificação de erro
            
        # O 'with TemporaryDirectory()' garante que temp_dir_str seja excluído automaticamente
        print(f"--- INGESTÃO CONCLUÍDA/FALHA para {original_filename} ---")


# ----------------------------------------------------------------------
# 3. ENDPOINT DA API
# ----------------------------------------------------------------------

@router.post("/upload")
async def process_drive_file(
    request: IngestionRequest, # <-- AGORA ACEITA O MODELO COMPLETO
    background_tasks: BackgroundTasks
):
    """
    Inicia a ingestão de um arquivo selecionado pelo usuário no Google Drive.
    A tarefa é movida para o background.
    """
    # Não precisamos mais da verificação not all([]) pois o Pydantic já garante que os campos existem.

    # Desempacota os dados do modelo para usar na lógica
    file_id = request.file_id
    user_id = request.user_id
    original_filename = request.original_filename

    # Verifica se o user_id possui credenciais válidas antes de iniciar
    # (Supondo que get_drive_service está corretamente importado)
    if not get_drive_service(user_id):
        raise HTTPException(
            status_code=401, 
            detail=f"Usuário {user_id} não autenticado ou token expirado. Por favor, reautentique."
        )

    # Adiciona a tarefa de processamento para ser executada em background
    # (Supondo que _process_drive_file_in_background está corretamente importado)
    background_tasks.add_task(
        _process_drive_file_in_background, 
        user_id, 
        file_id, 
        original_filename
    )
    
    # Retorna uma resposta HTTP 202 (Accepted) imediatamente.
    return {
        "status": "Processamento iniciado",
        "message": f"O processamento do arquivo '{original_filename}' foi iniciado em segundo plano.",
        "file_id": file_id
    }
