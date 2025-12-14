# app/services/document_analyzer.py

import re
from typing import List, Dict, Any, Tuple

# Definições de Regex (Mantidas)
REGEX_TITLE_OR_CHAPTER = re.compile(r"^\s*(TÍTULO|CAPÍTULO|SEÇÃO)\s+.*?\s*$", re.IGNORECASE | re.MULTILINE)
REGEX_ARTICLE = re.compile(r"^(Art\.|Artigo)\s+\d+\s*(\.\s*)?.*", re.IGNORECASE | re.MULTILINE)
REGEX_PARAGRAPH = re.compile(r"^\s*(\§\s+\d+|Parágrafo único\.|Parágrafo\s+\d+\.)", re.MULTILINE)

def analyze_law_structure(file_type: str, document_text: List[str]) -> List[Dict[str, Any]]:
    """
    Analisa o texto plano de uma Lei para identificar Artigos, Capítulos e Parágrafos.
    (O argumento 'file_type' é mantido apenas para compatibilidade de chamada).
    """
    print("-> Análise Estrutural: Identificando marcadores de Lei...")
    
    current_chapter = "Preâmbulo ou Seção Não Identificada"
    current_article = "Não Definido"
    section_data = []

    # O documento de texto é uma lista onde cada elemento é uma página (ou uma string gigante)
    full_text = "\n".join(document_text)

    # 1. Quebra Inicial por Artigo
    sections = re.split(REGEX_ARTICLE, full_text)

    # 2. Processamento do Preâmbulo
    i = 0
    if sections and sections[0].strip():
        # Trata o preâmbulo como um bloco inicial
        section_data.append({
            "text": sections[0],
            "metadata": {"chunk_type": "PREAMBULO", "chapter": current_chapter, "article": "N/A", "page_start": 1}
        })
        i = 1 # Começa a iteração nos marcadores de Artigo/Conteúdo

    # 3. Processamento dos Pares Artigo/Conteúdo
    while i < len(sections):
        
        # 3a. Busca pelo próximo Artigo Válido (Marker)
        article_marker = None
        while i < len(sections):
            candidate = sections[i]
            # Usa a REGEX para verificar se o item é um marcador válido
            if candidate is not None and isinstance(candidate, str) and candidate.strip():
                if REGEX_ARTICLE.search(candidate): 
                    article_marker = candidate
                    i += 1
                    break
            # Se for apenas um resíduo vazio/ponto, avança (ignora)
            i += 1 

        # Se o loop acima terminou e não encontrou um marcador, para.
        if article_marker is None:
            break
            
        # 3b. Busca pelo próximo Conteúdo Válido
        article_content = None
        j = i
        content_parts = []
        
        # O conteúdo é tudo que vier DEPOIS do marcador, até o próximo marcador de Artigo ou o final da lista.
        while j < len(sections):
            candidate = sections[j]
            # Verifica se o próximo item é um novo Artigo (Se for, o conteúdo terminou)
            if REGEX_ARTICLE.search(candidate):
                break
            
            # Adiciona o conteúdo (se não for vazio) e avança
            if candidate and candidate.strip():
                content_parts.append(candidate)
            j += 1
        
        # O conteúdo do Artigo é a junção das partes encontradas
        article_content = "\n".join(content_parts)
        
        # Atualiza o índice principal para o próximo item após o conteúdo
        i = j 

        # --- Se falhar ao encontrar conteúdo, ignora o Artigo e continua (ou trata como um resíduo) ---
        if not article_content.strip():
            print(f"AVISO: Marcador de Artigo encontrado ({article_marker.strip()}) sem conteúdo associado. Pulando.")
            continue # Vai para o próximo i

        # --- Lógica de Metadados (A lógica aqui permanece a mesma que já está funcionando) ---
        
        # ... (Sua lógica de extração de Capítulos e Artigos aqui) ...
        # (A lógica de extração que você já tem deve ser mantida aqui, 
        # usando `article_marker` e `article_content` que agora são strings válidas)
        
        # Exemplo da lógica anterior que deve ser mantida/colocada aqui:
        
        # Atualiza Capítulos
        chapter_match = REGEX_TITLE_OR_CHAPTER.search(article_marker)
        if chapter_match:
            current_chapter = chapter_match.group(0).strip()
        else:
            chapter_match_content = REGEX_TITLE_OR_CHAPTER.search(article_content)
            if chapter_match_content:
                current_chapter = chapter_match_content.group(0).strip()
        
        # Extrai o número do artigo
        article_match = re.search(r"\d+", article_marker)
        current_article = f"Artigo {article_match.group(0)}" if article_match else article_marker.strip()
        
        # Reconstrói a seção completa
        full_section_text = f"{article_marker.strip()}\n{article_content.strip()}"
        
        section_data.append({
            "text": full_section_text.strip(),
            "metadata": {
                "chunk_type": "LEGAL_ARTICLE",
                "chapter": current_chapter,
                "article": current_article,
                "page_start": "N/A" # Manter N/A se não houver lógica de página
            }
        })
        
    print(f"-> Análise Estrutural Concluída. {len(section_data)} seções identificadas.")
    return section_data
