# app/services/document_analyzer.py

import re
from typing import List, Dict, Any, Tuple

# Definições de Regex para Leis:
# 1. Título/Capítulo: Encontra linhas inteiras que parecem títulos grandes
REGEX_TITLE_OR_CHAPTER = re.compile(r"^\s*(TÍTULO|CAPÍTULO)\s+.*?\s*$", re.IGNORECASE | re.MULTILINE)

# 2. Artigo: Encontra "Art. X" ou "Artigo X" no início da linha
REGEX_ARTICLE = re.compile(r"^(Art\.|Artigo)\s+\d+\s*(\.\s*)?.*", re.IGNORECASE | re.MULTILINE)

# 3. Parágrafo: Encontra o símbolo de parágrafo (§) ou a palavra "Parágrafo"
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

    # O documento de texto é uma lista onde cada elemento é uma página (ou uma string gigante)
    full_text = "\n".join(document_text)

    # 1. Quebra Inicial por Artigo
    # Quebra o texto usando o Artigo como delimitador primário.
    # O Artigo encontrado é mantido no início do texto do chunk.
    sections = re.split(REGEX_ARTICLE, full_text)

    # O split retorna o Artigo em uma posição e o conteúdo dele na próxima
    if not sections or len(sections) < 2:
        print("AVISO: Nenhuma estrutura de Artigo detectada. Tratando como texto plano.")
        return [{"text": full_text, "metadata": {"chunk_type": "TEXT_BLOCK", "page_start": 1}}]

    # 2. Iterar sobre as Seções Encontradas
    i = 0
    # O primeiro elemento é o preâmbulo/início do documento
    if sections[0].strip():
        # Trata o preâmbulo como um bloco inicial
        section_data.append({
            "text": sections[0],
            "metadata": {"chunk_type": "PREAMBULO", "chapter": current_chapter, "article": "N/A", "page_start": 1}
        })
        i = 1

    # Itera sobre os pares (Artigo, Conteúdo)
    while i < len(sections):
        # O Artigo é o elemento 'i' e o conteúdo é o elemento 'i+1'
        article_marker = sections[i] if i < len(sections) else ""
        article_content = sections[i+1] if i+1 < len(sections) else ""
        
        # Reconstrói a seção completa
        full_section_text = f"{article_marker}{article_content}"
        
        # Atualiza Capítulos (busca dentro do conteúdo do artigo)
        chapter_match = REGEX_TITLE_OR_CHAPTER.search(full_section_text)
        if chapter_match:
            current_chapter = chapter_match.group(0).strip()
            # Remove o título/capítulo para que o chunk se concentre no conteúdo legal
            article_content = REGEX_TITLE_OR_CHAPTER.sub("", article_content).strip()

        # Extrai o número do artigo
        article_match = re.search(r"\d+", article_marker)
        current_article = f"Artigo {article_match.group(0)}" if article_match else article_marker.strip()
        
        section_data.append({
            "text": full_section_text.strip(), # O chunk será feito a partir deste texto
            "metadata": {
                "chunk_type": "LEGAL_ARTICLE",
                "chapter": current_chapter,
                "article": current_article,
                "page_start": "N/A" # Páginas serão atribuídas no chunking
            }
        })
        
        i += 2
        
    print(f"-> Análise Estrutural Concluída. {len(section_data)} seções identificadas.")
    return section_data


def analyze_document_structure(file_type: str, document_text: List[str]) -> List[Dict[str, Any]]:
    """Função orquestradora para análise estrutural baseada no tipo de documento."""
    
    # 1. Lógica Condicional
    if file_type in ['.pdf', '.txt', '.odt'] and 'Lei' in document_text[0][:100]:
        # Heurística simples: se for PDF/TXT/ODT e a primeira linha mencionar 'Lei', tenta o analisador de Lei.
        return analyze_law_structure(document_text)
    
    # 2. Fallback: Documentos simples (ou Livros sem análise estrutural implementada)
    print("-> Análise Estrutural: Usando Fallback de Texto Plano.")
    return [{"text": "\n".join(document_text), "metadata": {"chunk_type": "TEXT_BLOCK", "page_start": 1}}]
