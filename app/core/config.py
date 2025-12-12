# app/core/config.py
# (Trecho focado em Google Drive)

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # ... Outras configurações (Supabase, LLM Keys) ...
    EMBEDDING_MODEL_NAME: str
    # --- Configurações do Google Drive ---
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    # O URI para o qual o Google redirecionará após a autenticação
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/google/callback" 
    
    # Escopo (permissões) que sua aplicação precisa (leitura de arquivos)
    GOOGLE_SCOPES: list[str] = [
        "https://www.googleapis.com/auth/drive.readonly", # Apenas leitura
        "https://www.googleapis.com/auth/userinfo.email" # Opcional, para identificar o usuário
    ]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
