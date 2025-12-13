# app/routers/ingestion.py
from fastapi import APIRouter, File, UploadFile, HTTPException, BackgroundTasks
from uuid import uuid4
import os
import io
import traceback
from pathlib import Path
from tempfile import TemporaryDirectory
from googleapiclient.http import MediaIoBaseDownload
from typing import Optional

# Importações dos Services e Core
from ..services.document_loader import handle_document_load_from_path # Funçao precisa ser adaptada para PATH
from ..services.ocr_processor import refine_extracted_content
from ..services.vector_db_manager import run_ingestion_pipeline
from ..core.drive_auth import get_drive_service # Cliente do Google Drive
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel # <-- Importação do BaseModel


# --- NOVO: Modelo Pydantic para o Corpo da Requisição ---
class IngestionRequest(BaseModel):
    file_id: str
    user_id: str
    original_filename: str
    
    class Config:
        # Exemplo que aparecerá no Swagger UI
        json_schema_extra = {
            "example": {
                "file_id": "1A2B3C4D5E6F7G8H9I0J",
                "user_id": "<SEU_GOOGLE_CLIENT_ID>",
                "original_filename": "documento_secreto.pdf"
            }
        }

router = APIRouter(prefix="/ingestion", tags=["Ingestão"])

# ----------------------------------------------------------------------
# 1. FUNÇÃO AUXILIAR DE DOWNLOAD
# ----------------------------------------------------------------------
from googleapiclient.http import MediaIoBaseDownload
from pathlib import Path
import io

# Adicione o dicionário de tipos nativos que precisam de exportação
# Este mapeamento é crucial para a solução.
GOOGLE_NATIVE_MIME_TYPES = {
    'application/vnd.google-apps.document': 'application/pdf',  # Google Docs -> PDF
    'application/vnd.google-apps.spreadsheet': 'application/pdf', # Google Sheets -> PDF
    'application/vnd.google-apps.presentation': 'application/pdf', # Google Slides -> PDF
    # Adicione outros tipos nativos se necessário
}

async def download_file_from_drive(service, file_id: str, filename: str, temp_dir: Path) -> Path:
    """
    Faz o download de um arquivo do Google Drive para um caminho temporário, 
    lidando com arquivos nativos (exportando para PDF) e não-nativos.
    """
    
    # 1. OBTER METADADOS (para determinar o tipo de arquivo)
    # Precisamos do mimeType para saber se devemos usar GET ou EXPORT
    metadata = service.files().get(fileId=file_id, fields='mimeType').execute()
    mime_type = metadata.get('mimeType')
    print(f"DEBUG: Tipo MIME do arquivo {file_id}: {mime_type}")

    temp_file_path = temp_dir / filename
    request = None

    if mime_type in GOOGLE_NATIVE_MIME_TYPES:
        # 2. SE FOR ARQUIVO NATIVO DO GOOGLE (ex: Docs), USAR EXPORTAÇÃO
        export_mime = GOOGLE_NATIVE_MIME_TYPES[mime_type]
        print(f"DEBUG: Arquivo nativo detectado. Exportando como: {export_mime}")
        
        # O nome do arquivo DEVE refletir a conversão para PDF, caso contrário, 
        # o document_loader falhará ao tentar ler um .docx como .pdf.
        if not filename.lower().endswith('.pdf'):
            temp_file_path = temp_dir / f"{temp_file_path.stem}.pdf"
            print(f"DEBUG: Novo caminho de arquivo: {temp_file_path}")

        request = service.files().export_media(
            fileId=file_id,
            mimeType=export_mime
        )
    else:
        # 3. SE FOR ARQUIVO BINÁRIO (ex: PDF, DOCX, JPG), USAR GET_MEDIA
        print("DEBUG: Arquivo binário detectado. Usando get_media.")
        request = service.files().get_media(fileId=file_id)

    # Inicia o download
    fh = io.FileIO(temp_file_path, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    
    while done is False:
        # O erro HttpError ocorria aqui se request fosse um GET em um Google Doc
        status, done = downloader.next_chunk()
        # print(f"Download {int(status.progress() * 100)}% de {filename}.")
            
    print("DEBUG: Download concluído com sucesso.")
    return temp_file_path

# ----------------------------------------------------------------------
# 2. FUNÇÃO PRINCIPAL DE PROCESSAMENTO EM BACKGROUND
# ----------------------------------------------------------------------

async def _process_drive_file_in_background(user_id: str, file_id: str, original_filename: str):
    """
    Função wrapper que executa o pipeline de ingestão completo para um arquivo do Drive.
    (Com logs de debug e traceback detalhado para diagnóstico de falha)
    """
    document_id = str(uuid4())
    print(f"\n--- INGESTÃO INICIADA para {original_filename} (ID: {document_id}) ---")

    drive_service = get_drive_service(user_id)
    if not drive_service:
        print(f"ERRO: Serviço do Drive indisponível para o usuário {user_id}. Reautenticação necessária.")
        return

    # Usamos TemporaryDirectory para garantir que o arquivo temporário seja excluído no final
    with TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        temp_file_path: Optional[Path] = None

        try:
            # 1. DOWNLOAD (do Drive para o disco temporário)
            print("DEBUG: Etapa 1: Iniciando download do Drive...")
            temp_file_path = await download_file_from_drive(
                drive_service, 
                file_id, 
                original_filename, 
                temp_dir
            )
            print(f"DEBUG: Etapa 1 concluída. Arquivo salvo em: {temp_file_path}")
            
            # 2. CARREGAMENTO (app/services/document_loader.py)
            print("DEBUG: Etapa 2: Iniciando handle_document_load_from_path...")
            document_text, document_images, file_type = await handle_document_load_from_path(
                temp_file_path, 
                original_filename
            )
            print("DEBUG: Etapa 2 concluída. Documento carregado.")
            
            # 3. REFINAMENTO (PLUMBER - app/services/ocr_processor.py)
            print("DEBUG: Etapa 3: Iniciando refine_extracted_content (Plumber)...")
            refined_content = await refine_extracted_content(
                document_text, 
                document_images, 
                file_type
            )
            print("DEBUG: Etapa 3 concluída. Conteúdo refinado.")
            
            # 4. PIPELINE FINAL (app/services/vector_db_manager.py)
            print("DEBUG: Etapa 4: Iniciando run_ingestion_pipeline (Chunking/Embedding/DB)...")
            success = await run_ingestion_pipeline(
                refined_content, 
                document_id 
                #original_filename
            )
            print("DEBUG: Etapa 4 concluída: Inserção no DB.")
            
            if not success:
                raise Exception("A inserção final no banco de dados falhou.")
                
            print(f"--- INGESTÃO CONCLUÍDA COM SUCESSO para {original_filename} ---")

        except Exception as e:
            # CORREÇÃO CRÍTICA: Imprime a pilha de erros completa
            print("---------------------------------------------------------")
            print(f"ERRO DE INGESTÃO CRÍTICO no arquivo {original_filename} (ID: {document_id}):")
            
            # Imprime a pilha de execução completa, mostrando a linha exata da falha
            traceback.print_exc() 
            
            # Imprime o erro em sua representação (útil para erros sem mensagem de string)
            print(f"\n--- Mensagem de Erro Bruta: {repr(e)} ---") 
            print("---------------------------------------------------------")
            
        # O 'with TemporaryDirectory()' garante que o arquivo temporário seja excluído
        print(f"--- FIM DO PROCESSAMENTO para {original_filename} ---")


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
