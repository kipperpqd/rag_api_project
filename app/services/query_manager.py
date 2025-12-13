# app/services/query_manager.py

import os
from openai import OpenAI
from supabase import Client
from typing import List, Dict

# Assumimos que o cliente Supabase e OpenAI estão acessíveis
# (Você pode precisar importar eles de onde foram inicializados em vector_db_manager)
from .vector_db_manager import supabase, openai_client, EMBEDDING_MODEL # Importa as variáveis globais

# --- CONFIGURAÇÃO ---
RAG_K = 5 # Número de chunks mais relevantes para recuperar
LLM_MODEL = "gpt-4o"

async def run_query_pipeline(user_query: str) -> str:
    
    if not supabase or not openai_client:
        return "ERRO: O serviço de IA ou Banco de Dados não está inicializado."

    # 1. Gerar o Embedding da Query
    try:
        print(f"-> Gerando embedding para a query: '{user_query[:30]}...'")
        query_embedding_response = openai_client.embeddings.create(
            input=[user_query],
            model=EMBEDDING_MODEL
        )
        query_vector = query_embedding_response.data[0].embedding
        print("-> Embedding da Query gerado com sucesso.")
    except Exception as e:
        print(f"ERRO DE EMBEDDING DA QUERY: {e}")
        return "Falha ao processar a pergunta."

    # 2. Recuperação Vetorial (Busca no Supabase)
    try:
        print(f"-> Buscando os {RAG_K} chunks mais relevantes no Supabase...")
        
        # O Supabase Client e a função 'match_documents' usam a função pgvector no SQL
        response = (
            supabase.rpc(
                'match_documents', 
                {
                    'query_embedding': query_vector, 
                    'match_count': RAG_K,
                }
            )
            .execute()
        )
        
        # Os resultados são os chunks recuperados
        relevant_chunks = response.data 
        print(f"-> Recuperados {len(relevant_chunks)} chunks relevantes.")

    except Exception as e:
        print(f"ERRO DE BUSCA VETORIAL: {e}")
        return "Falha ao buscar contexto no banco de dados."


    # 3. Montar o Prompt de Contexto (Augmented Prompt)
    
    if not relevant_chunks:
        return f"Não foi encontrado conteúdo relevante no documento para responder: {user_query}"
        
    context_text = "\n---\n".join([chunk['content'] for chunk in relevant_chunks])

    # Instruções para o LLM
    system_prompt = (
        "Você é um assistente RAG (Retrieval-Augmented Generation) especializado em responder "
        "perguntas estritamente com base no contexto fornecido abaixo. "
        "Se a resposta não puder ser encontrada no contexto, diga claramente 'Não consegui encontrar esta informação nos documentos fornecidos.' "
        "Não invente ou utilize conhecimento prévio."
    )
    
    user_prompt = (
        f"Contexto Recuperado:\n{context_text}\n\n"
        f"Pergunta do Usuário: {user_query}"
    )

    # 4. Geração (Chamar o LLM)
    try:
        print("-> Gerando resposta final com o LLM...")
        
        llm_response = openai_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        
        final_answer = llm_response.choices[0].message.content
        print("-> Resposta do LLM gerada com sucesso.")
        return final_answer

    except Exception as e:
        print(f"ERRO DE GERAÇÃO DO LLM: {e}")
        return "Falha ao gerar a resposta final pelo modelo de linguagem."
