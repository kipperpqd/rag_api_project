# app/core/config.py
# (Trecho focado em Google Drive)

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # ... Outras configurações (Supabase, LLM Keys) ...
    EMBEDDING_MODEL_NAME: str
    EMBEDDING_DIMENSION: str
    GENERATION_MODEL_NAME: str
    LLM_API_KEY: str

    # URL da sua instância Supabase (Coolify ou serviço externo)
    SUPABASE_URL: str
    # Chave de serviço (service_role key) para o backend, para acesso total (Ingestão)
    SUPABASE_SERVICE_KEY: str
    # Nome da tabela onde os chunks e embeddings serão armazenados
    SUPABASE_TABLE_NAME: str


    # --- Configurações do Google Drive ---
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    # O URI para o qual o Google redirecionará após a autenticação
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/google/callback" 
    
    # Escopo (permissões) que sua aplicação precisa (leitura de arquivos)
    GOOGLE_SCOPES: List[str] = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/drive.readonly"
    ]
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
