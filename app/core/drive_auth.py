# app/core/drive_auth.py
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from typing import Optional, Dict
import json
from .config import settings
import os

# Caminho para armazenar o token do usuário (Idealmente, usaria um DB seguro, como Supabase)
TOKEN_STORAGE_PATH = "tokens.json" 

def save_credentials(user_id: str, credentials: Credentials):
    """Salva as credenciais (incluindo o Refresh Token) de um usuário."""
    # Em um produto real, isso seria criptografado e armazenado no Supabase/DB.
    # Aqui, usaremos um arquivo simples para o conceito.
    data = {}
    if os.path.exists(TOKEN_STORAGE_PATH):
        with open(TOKEN_STORAGE_PATH, 'r') as f:
            data = json.load(f)

    data[user_id] = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }
    with open(TOKEN_STORAGE_PATH, 'w') as f:
        json.dump(data, f)
    print(f"Credenciais salvas para o usuário: {user_id}")

def get_drive_service(user_id: str) -> Optional[build]:
    """
    Retorna o objeto de serviço do Google Drive API para um usuário específico.
    Se o Access Token estiver expirado, ele usa o Refresh Token para gerar um novo.
    """
    if not os.path.exists(TOKEN_STORAGE_PATH):
        return None

    with open(TOKEN_STORAGE_PATH, 'r') as f:
        data = json.load(f)

    if user_id not in data:
        return None
        
    user_data = data[user_id]
    
    # 1. Cria o objeto Credentials
    creds = Credentials.from_authorized_user_info(user_data)
    
    # 2. Se o Access Token for inválido, tenta renová-lo
    if not creds.valid:
        if creds.refresh_token:
            creds.refresh(Request())
            # Salva o novo token (que pode ter mudado)
            save_credentials(user_id, creds)
        else:
            # Necessita reautenticação manual (muito raro se o Refresh Token for persistente)
            return None

    # 3. Constrói e retorna o objeto de serviço (o cliente real do Drive)
    service = build('drive', 'v3', credentials=creds)
    return service

# --- Funções para a rota de autenticação ---

def get_google_auth_flow() -> Flow:
    """Cria e retorna o objeto Flow para iniciar o processo de autenticação."""
    return Flow.from_client_config(
        client_config={
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        },
        scopes=settings.GOOGLE_SCOPES,
        redirect_uri=settings.GOOGLE_REDIRECT_URI
    )
