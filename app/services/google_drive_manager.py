# app/services/google_drive_manager.py
from ..services.google_drive_manager import (
    download_drive_file, get_resource_metadata, list_files_in_folder, DRIVE_MIME_TYPES
)
# ... (Suas importações e funções existentes: get_drive_service, download_drive_file) ...

DRIVE_MIME_TYPES = {
    'folder': 'application/vnd.google-apps.folder',
    'document': 'application/vnd.google-apps.document',
    # Adicione outros MimeTypes conforme necessário para o Plumber
}

async def get_resource_metadata(user_id: str, resource_id: str) -> dict | None:
    """Obtém os metadados básicos de um arquivo ou pasta."""
    service = get_drive_service(user_id)
    try:
        # Usa fields para obter apenas o que precisamos (nome e tipo MIME)
        file = service.files().get(fileId=resource_id, fields='id, name, mimeType').execute()
        return file
    except Exception as e:
        print(f"ERRO: Não foi possível obter metadados para ID {resource_id}: {e}")
        return None


async def list_files_in_folder(user_id: str, folder_id: str) -> List[Dict]:
    """Lista todos os arquivos dentro de uma pasta do Drive, exceto pastas aninhadas."""
    service = get_drive_service(user_id)
    files_to_process = []
    
    # Query para buscar arquivos DENTRO da pasta e excluir subpastas.
    # mimeType != 'application/vnd.google-apps.folder' garante que não listamos subpastas.
    # trashed=false garante que não listamos arquivos na lixeira.
    query = f"'{folder_id}' in parents and mimeType != '{DRIVE_MIME_TYPES['folder']}' and trashed=false"
    
    try:
        results = service.files().list(
            q=query,
            pageSize=100, # Limite de itens por página
            fields="nextPageToken, files(id, name, mimeType)"
        ).execute()
        
        files_to_process.extend(results.get('files', []))

        # Adicione lógica de paginação se for trabalhar com mais de 100 arquivos
        # (Opcional por enquanto, mas necessário para uso em produção)
        
        return files_to_process
        
    except Exception as e:
        print(f"ERRO: Falha ao listar arquivos na pasta {folder_id}: {e}")
        return []
