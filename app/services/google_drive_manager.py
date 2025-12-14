# app/services/google_drive_manager.py

import os
import io
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Tuple, List, Dict

from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ..core.drive_auth import get_drive_service # Assumindo que o get_drive_service é importado daqui

# --- CONSTANTES DE TIPO MIME ---
DRIVE_MIME_TYPES = {
    'folder': 'application/vnd.google-apps.folder',
    'document': 'application/vnd.google-apps.document',
    # Adicione outros MimeTypes de arquivos binários suportados (ex: 'application/pdf')
}

# Mapeamento de MimeTypes NATIVOS do Google para o formato de EXPORTAÇÃO (geralmente PDF)
GOOGLE_NATIVE_MIME_TYPES = {
    'application/vnd.google-apps.document': 'application/pdf',  # Google Docs -> PDF
    'application/vnd.google-apps.spreadsheet': 'application/pdf', # Google Sheets -> PDF
    'application/vnd.google-apps.presentation': 'application/pdf', # Google Slides -> PDF
    # Adicione outros tipos nativos se necessário
}

# ----------------------------------------------------------------------
# 1. FUNÇÕES DE METADADOS
# ----------------------------------------------------------------------

async def get_resource_metadata(user_id: str, resource_id: str) -> dict | None:
    """Obtém os metadados básicos (nome e tipo MIME) de um recurso (arquivo ou pasta)."""
    service = get_drive_service(user_id)
    if not service:
        print(f"ERRO: Serviço do Drive não disponível para o usuário {user_id}.")
        return None
        
    try:
        # Usa fields para obter apenas o que precisamos (nome e tipo MIME)
        file = service.files().get(fileId=resource_id, fields='id, name, mimeType').execute()
        return file
    except HttpError as e:
        if e.resp.status == 404:
            print(f"ERRO 404: Recurso Drive {resource_id} não encontrado.")
        elif e.resp.status == 403:
            print(f"ERRO 403: Permissão negada para acessar o recurso {resource_id}.")
        else:
            print(f"ERRO HTTP ao obter metadados para ID {resource_id}: {e}")
        return None
    except Exception as e:
        print(f"ERRO: Não foi possível obter metadados para ID {resource_id}: {e}")
        return None


async def list_files_in_folder(user_id: str, folder_id: str) -> List[Dict]:
    """Lista todos os arquivos válidos dentro de uma pasta, excluindo subpastas."""
    service = get_drive_service(user_id)
    if not service:
        return []
        
    files_to_process = []
    
    # Query: buscar arquivos DENTRO da pasta, excluir subpastas e itens na lixeira.
    #query = f"'{folder_id}' in parents and mimeType != '{DRIVE_MIME_TYPES['folder']}' and trashed=false"
    query = f"'{folder_id}' in parents and trashed=false"
    try:
        # Busca recursiva com paginação (caso haja mais de 100 arquivos)
        page_token = None
        while True:
            results = service.files().list(
                q=query,
                pageSize=100,
                fields="nextPageToken, files(id, name, mimeType)",
                pageToken=page_token
            ).execute()
            
            files_to_process.extend(results.get('files', []))
            page_token = results.get('nextPageToken')
            
            if page_token is None:
                break
                
        return files_to_process
        
    except Exception as e:
        print(f"ERRO: Falha ao listar arquivos na pasta {folder_id}: {e}")
        return []

# ----------------------------------------------------------------------
# 2. FUNÇÃO PRINCIPAL DE DOWNLOAD (SUPORTE A EXPORTAÇÃO)
# ----------------------------------------------------------------------

async def download_drive_file(user_id: str, file_id: str, filename: str, temp_dir_path: str) -> str | None:
    """
    Faz o download de um arquivo do Google Drive para o diretório temporário fornecido. 
    Retorna apenas o caminho completo do arquivo baixado (ou None em caso de falha).
    """
    service = get_drive_service(user_id)
    if not service:
        return None
        
    # O caminho do diretório temporário é recebido como string
    temp_file_path = Path(temp_dir_path) / filename
    
    print(f"DEBUG: Iniciando download para caminho temporário: {temp_dir_path}")

    try:
        # Obter MIME Type
        metadata = service.files().get(fileId=file_id, fields='mimeType').execute()
        mime_type = metadata.get('mimeType')
        print(f"DEBUG: Tipo MIME do arquivo {file_id}: {mime_type}")

        request = None
        
        if mime_type in GOOGLE_NATIVE_MIME_TYPES:
            # Arquivo nativo do Google (Docs, Sheets, Slides) -> USAR EXPORT
            export_mime = GOOGLE_NATIVE_MIME_TYPES[mime_type]
            print(f"DEBUG: Arquivo nativo detectado. Exportando como: {export_mime}")
            
            # Garante que a extensão final é .pdf para o document_loader
            if not filename.lower().endswith('.pdf'):
                temp_file_path = Path(temp_dir_path) / f"{Path(filename).stem}.pdf"
                
            request = service.files().export_media(
                fileId=file_id,
                mimeType=export_mime
            )
        else:
            # Arquivo binário (PDF, DOCX, TXT, etc.) -> USAR GET_MEDIA
            print("DEBUG: Arquivo binário detectado. Usando get_media.")
            request = service.files().get_media(fileId=file_id)

        # Inicia o download
        fh = io.FileIO(temp_file_path, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        
        while done is False:
            status, done = downloader.next_chunk()
            
        print(f"DEBUG: Download de {filename} concluído com sucesso em {temp_file_path}")
        return str(temp_file_path) # Retorna APENAS o caminho do arquivo
        
    except Exception as e:
        print(f"ERRO: Falha no download ou exportação do arquivo {file_id}: {e}")
        # NENHUMA LIMPEZA AQUI! O chamador é responsável pelo TemporaryDirectory.
        return None
