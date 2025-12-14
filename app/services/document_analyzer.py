# app/services/document_analyzer.py

import re
from typing import List, Dict, Any, Tuple

# Definições de Regex (Mantidas)
REGEX_TITLE_OR_CHAPTER = re.compile(r"^\s*(TÍTULO|CAPÍTULO|SEÇÃO)\s+.*?\s*$", re.IGNORECASE | re.MULTILINE)
REGEX_ARTICLE = re.compile(r"^(Art\.|Artigo)\s+\d+\s*(\.\s*)?.*", re.IGNORECASE | re.MULTILINE)
REGEX_PARAGRAPH = re.compile(r"^\s*(\§\s+\d+|Parágrafo único\.|Parágrafo\s+\d+\.)", re.MULTILINE)


def analyze_law_structure(document_text: List[str]) -> List[Dict[str, Any]]:
    """
    Analisa o texto plano de uma Lei para identificar Artigos, Capítulos e Parágrafos.
    Retorna uma lista de seções com metadados para guiar o chunking.
    """
    print("-> Análise Estrutural: Identificando marcadores de Lei...")
    
    current_chapter = "Preâmbulo ou Seção Não Identificada"
    current_article = "Não Definido"
    section_data = []

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
    # O loop deve garantir que sempre haja um par (marcador, conteúdo) para processar.
    while i < len(sections):
        
        # Garante que haja pelo menos o marcador e o conteúdo (i e i+1)
        if i + 1 >= len(sections):
            # Se sobrar apenas um elemento no final (que é um marcador sem conteúdo ou resquício)
            if sections[i].strip():
                print(f"AVISO: Bloco final sem par de conteúdo: {sections[i][:50]}...")
                section_data.append({
                    "text": sections[i],
                    "metadata": {"chunk_type": "RESIDUO", "chapter": current_chapter, "article": "N/A", "page_start": 1}
                })
            break # Sai do loop se não houver um par completo
            
        # Define o marcador (Artigo) e o conteúdo (Texto)
        article_marker = sections[i] 
        article_content = sections[i+1]
        
        # Se algum deles não for uma string (por alguma falha interna do split), pula o par
        if not isinstance(article_marker, str) or not isinstance(article_content, str):
            print(f"ERRO: Encontrado valor não-string no índice {i}. Pulando par.")
            i += 2
            continue

        # --- Lógica de Metadados ---
        
        # Atualiza Capítulos (busca dentro do conteúdo, pois a quebra foi feita por Artigo)
        # Usamos o marcador (article_marker) e o conteúdo (article_content)
        chapter_match = REGEX_TITLE_OR_CHAPTER.search(article_marker)
        if chapter_match:
            current_chapter = chapter_match.group(0).strip()
        else:
            # Tenta encontrar no conteúdo também, caso o Artigo tenha sido o delimitador primário
            chapter_match_content = REGEX_TITLE_OR_CHAPTER.search(article_content)
            if chapter_match_content:
                current_chapter = chapter_match_content.group(0).strip()
        
        # Extrai o número do artigo (Esta era a linha que falhava!)
        # O re.search agora recebe um string válido (article_marker)
        article_match = re.search(r"\d+", article_marker)
        
        # Cria o identificador do Artigo
        current_article = f"Artigo {article_match.group(0)}" if article_match else article_marker.strip()
        
        # Reconstrói a seção completa
        full_section_text = f"{article_marker}{article_content}"
        
        section_data.append({
            "text": full_section_text.strip(),
            "metadata": {
                "chunk_type": "LEGAL_ARTICLE",
                "chapter": current_chapter,
                "article": current_article,
                "page_start": "N/A"
            }
        })
        
        i += 2 # Avança para o próximo par (marcador, conteúdo)
        
    print(f"-> Análise Estrutural Concluída. {len(section_data)} seções identificadas.")
    return section_data
