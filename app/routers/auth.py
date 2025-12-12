# app/routers/auth.py
from fastapi import APIRouter, HTTPException, Query, Request
from typing import Optional
from starlette.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from fastapi import APIRouter # Importa o router padrão do FastAPI
# Inicializa o router
router = APIRouter(
    prefix="/auth", 
    tags=["Autenticação Google"]
)
# Importações dos Core Services

from ..core.drive_auth import get_google_auth_flow, save_credentials
from ..core.config import settings

@router.get("/google/start")
async def google_auth_start():
    """
    Inicia o fluxo OAuth 2.0. Redireciona o usuário para a página de consentimento do Google.
    
    Atenção: A URL de redirecionamento (redirect_uri) deve estar configurada no Google Cloud Console.
    """
    try:
        # 1. Cria o objeto de fluxo de autenticação
        flow = get_google_auth_flow()
        
        # 2. Gera a URL de autorização e o estado (state)
        # O prompt='consent' força o usuário a re-autorizar, garantindo o refresh token.
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent' 
        )
        
        # 3. Armazena o 'state' na sessão (ou em um cookie/DB temporário)
        # Neste exemplo conceitual, estamos ignorando a persistência do state,
        # mas em produção isso é VITAL para evitar ataques CSRF.
        print(f"DEBUG: STATE gerado (DEVE SER PERSISTIDO): {state}")

        # 4. Redireciona o usuário para o Google
        return RedirectResponse(authorization_url)
    
    except Exception as e:
        print(f"Erro ao iniciar autenticação Google: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao iniciar a autenticação.")


@router.get("/callback")
async def google_auth_callback(
    code: str = Query(..., description="Código de autorização retornado pelo Google."),
    state: Optional[str] = Query(None, description="Estado anti-CSRF retornado pelo Google.")
):
    """
    Endpoint de Callback. Recebe o código do Google e troca por tokens de acesso.
    """
    try:
        # 1. Verificar o 'state' (CRUCIAL para segurança)
        # TODO: Implementar a checagem do state aqui (comparar com o state persistido)
        # if state != state_persistido_anteriormente:
        #     raise HTTPException(status_code=400, detail="State inválido. Possível ataque CSRF.")
            
        # 2. Recria o objeto de fluxo
        flow = get_google_auth_flow()
        
        # 3. Troca o código pela credencial
        # O código de autorização só pode ser usado uma vez
        flow.fetch_token(code=code)
        
        # 4. Obtém as credenciais completas
        credentials = flow.credentials
        
        # 5. Opcional: Obtém o user_id real do Google
        # Isso é necessário para usar a chave do usuário no nosso Supabase
        # Para simplificar, usaremos o ID do cliente como user_id (NÃO IDEAL em produção)
        user_id = credentials.client_id 
        
        # 6. Salva as credenciais no nosso sistema (app/core/drive_auth.py)
        # Isso salva o Refresh Token, que é usado para acesso contínuo.
        save_credentials(user_id, credentials)
        
        # 7. Resposta final para o usuário
        return {
            "status": "Autenticação bem-sucedida!",
            "message": f"Seu Google Drive foi conectado. User ID: {user_id}",
            "next_step": "Agora você pode usar o User ID na tela de ingestão para processar seus arquivos."
        }
        
    except HTTPException:
        # Permite que erros HTTP de segurança (como state inválido) sejam propagados
        raise
    except Exception as e:
        print(f"Erro ao processar callback: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao finalizar a autenticação.")
