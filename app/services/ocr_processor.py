# app/services/ocr_processor.py
from typing import List, Dict, Any, Tuple, Union
from PIL import Image
# Se for usar Tesseract para OCR tradicional (opcional)
from pytesseract import image_to_string 

# Importações dos Core Services
from ..core.llm_clients import get_multimodal_llm_client # Cliente LLM para visão
# from ..core.config import settings # Para configurações, se necessário
from pathlib import Path
import pdfplumber

# Definição de tipo customizado para o resultado consolidado (usado em vector_db_manager)
ConsolidatedText = List[Dict[str, Union[str, int, str]]] 
# Placeholder para imagens (tipo usado pelo PIL)
ImageObject = Image.Image 

# --- Constantes para o Loader ---
# Esta constante é usada para identificar páginas onde o pdfplumber falhou
CONTENT_MISSING_TEXTUAL = "CONTENT_MISSING_TEXTUAL" 
# Heurística: se o texto extraído for menor que isso, provavelmente é uma imagem
MIN_TEXT_FOR_HEURISTIC = 100 


# ----------------------------------------------------------------------
# 1. FUNÇÕES AUXILIARES DE PROCESSAMENTO (OCR e LLM)
# ----------------------------------------------------------------------

def run_traditional_ocr(image_data: ImageObject) -> str:
    """
    Executa OCR tradicional (via PyTesseract) em uma imagem.
    Útil para texto escaneado ou falhas do pdfplumber.
    """
    try:
        # Usa o idioma português ('por') e inglês ('eng') para maior cobertura
        ocr_text = image_to_string(image_data, lang='por+eng')
        return ocr_text.strip()
    except Exception as e:
        # Tesseract pode falhar se a imagem for ruim
        print(f"AVISO: Falha no OCR Tradicional: {e}")
        return ""


async def describe_visual_element(image_data: ImageObject, context: str, page_number: int) -> str:
    """
    Chama a API do LLM Multimodal (Ex: Gemini ou GPT-4o) para gerar uma 
    descrição detalhada do elemento visual (mapa, gráfico, diagrama).
    """
    
    llm_client = get_multimodal_llm_client()
    
    # 1. Constrói o Prompt (A Engenharia de Prompt para Multimodal é crucial!)
    prompt = f"""
    Sua tarefa é analisar a imagem da página {page_number} e gerar uma descrição textual completa e detalhada, ideal para um sistema de Perguntas e Respostas (RAG). 
    
    INSTRUÇÕES:
    1. Se for um gráfico ou mapa, descreva os dados, tendências, legendas e informações geográficas relevantes.
    2. Se for uma tabela, transcreva os dados chave em formato de texto.
    3. Se for apenas texto escaneado, transcreva o texto usando o OCR.
    4. Mantenha o tom formal e informativo.
    
    Contexto da página: {context[:1000]} (Use este texto circundante para guiar a análise).
    
    Formato de Saída Desejado: [TIPO: Mapa/Gráfico/Tabela/OCR] [DESCRIÇÃO DETALHADA AQUI]
    """
    
    # 2. Prepara o conteúdo (Imagem + Prompt)
    # O cliente LLM deve ser capaz de receber tanto a string do prompt quanto o objeto ImageObject
    content = [prompt, image_data]
    
    # 3. Chamada Assíncrona à API
    print(f"-> Chamando LLM Multimodal para Page {page_number}...")
    
    try:
        # Supondo que o llm_client.generate_content seja a função de chamada da API
        response = await llm_client.generate_content(content)
        return response.text.strip()
    except Exception as e:
        print(f"ERRO LLM Multimodal na página {page_number}: {e}")
        # Retorna um fallback de erro
        return f"[ERRO LLM] Não foi possível obter descrição multimodal para a página {page_number}. Erro: {e}"

# ----------------------------------------------------------------------
# 1.5 FUNÇÃO DE PRÉ-OCR (Orquestração Tesseract)
# ----------------------------------------------------------------------

def orchestrate_pre_ocr(file_path: Path) -> List[str]:
    """
    Orquestra o OCR tradicional (PyTesseract) para um PDF escaneado.
    Itera sobre as páginas, converte para imagem e executa o OCR.
    Retorna uma lista de strings, uma por página.
    """
    print(f"-> OCR Tradicional: Iniciando pré-processamento OCR para {file_path.name}")
    ocr_text_by_page = []
    
    try:
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages):
                
                # Renderiza a página como imagem (Requer Poppler instalado)
                try:
                    page_image = page.to_image(resolution=300) # Alta resolução para melhor OCR
                    image_data: ImageObject = page_image.original # Objeto PIL Image
                    
                    ocr_result = run_traditional_ocr(image_data)
                    
                    if ocr_result.strip():
                        print(f"-> OCR Tradicional: Texto extraído da página {i+1} ({len(ocr_result)} chars).")
                        ocr_text_by_page.append(ocr_result)
                    else:
                        print(f"-> OCR Tradicional: Nenhuma saída na página {i+1}.")
                        ocr_text_by_page.append(CONTENT_MISSING_TEXTUAL)
                        
                except Exception as page_e:
                    print(f"AVISO: Falha ao processar página {i+1} para OCR (Poppler/Tesseract): {page_e}")
                    ocr_text_by_page.append(CONTENT_MISSING_TEXTUAL)
                    
        return ocr_text_by_page
        
    except Exception as e:
        print(f"ERRO: Falha na orquestração de pré-OCR para {file_path.name}: {e}")
        return []

# ----------------------------------------------------------------------
# 2. FUNÇÃO PRINCIPAL: ORQUESTRAÇÃO
# ----------------------------------------------------------------------

async def refine_extracted_content(
    document_text: List[str], 
    document_images: List[ImageObject], # Agora usa o tipo ImageObject
    file_type: str
) -> ConsolidatedText:
    """
    Orquestra o processo de refinamento, usando OCR e LLM Multimodal quando necessário.
    
    Args:
        document_text: Lista de texto por página (saída do document_loader).
        document_images: Lista de imagens (somente para PDF/Imagens, caso contrário, vazia).
        file_type: Extensão do arquivo (ex: '.pdf').
        
    Returns:
        Lista de dicionários, onde cada item é um chunk pronto para metadados/inserção.
    """
    consolidated_data = []

    # 1. Caso Simples: Arquivos sem Imagens (DOCX, TXT, PPTX)
    if file_type != '.pdf' or not document_images:
        # Assumimos que o texto primário (DOCX/TXT) é o resultado final
        for i, text in enumerate(document_text):
            if text.strip() or i < 1: # Garante que haja pelo menos um item
                consolidated_data.append({
                    "page_number": i + 1,
                    "content_type": "TEXT",
                    "text": text,
                    "metadata_source": f"{file_type.upper()}_LOADER"
                })
        return consolidated_data

    # 2. Lógica de Refinamento de PDF (OCR + Multimodal)
    print("\n--- Iniciando Refinamento Multimodal do PDF ---")
    
    # Itera sobre o menor número de elementos para evitar IndexError
    num_pages = min(len(document_text), len(document_images)) 

    for i in range(num_pages):
        page_number = i + 1
        text_page = document_text[i]
        image_data = document_images[i]

        # HEURÍSTICA: Decide quando usar a inteligência avançada (LLM Multimodal)
        is_text_missing_or_short = (
            text_page == CONTENT_MISSING_TEXTUAL or 
            len(text_page.strip()) < MIN_TEXT_FOR_HEURISTIC
        )
        
        if is_text_missing_or_short:
            # CHAMADA INTELIGENTE: Usar LLM Multimodal na imagem
            print(f"Página {page_number}: Texto nativo insuficiente. Usando LLM Multimodal.")
            
            # Chama o LLM (passando o texto nativo curto como 'context')
            rich_description = await describe_visual_element(image_data, text_page, page_number)
            
            content_type = "VISUAL_DESCRIPTION"
            final_text = rich_description
            source = "LLM_MULTIMODAL"
            
        else:
            # EXTRAÇÃO NORMAL: Assumimos que o texto nativo é suficiente
            print(f"Página {page_number}: Texto nativo OK. Assumindo texto limpo.")
            
            # Opcional: Rodar OCR simples para complementar (se quiser garantir texto escondido)
            # ocr_supplement = run_traditional_ocr(image_data)
            # final_text = text_page + "\n" + ocr_supplement
            
            final_text = text_page
            content_type = "TEXT"
            source = "PDFPLUMBER"
            
        # 3. Consolidar o resultado para o Chunking
        consolidated_data.append({
            "page_number": page_number,
            "content_type": content_type,
            "text": final_text,
            "metadata_source": source
        })

    print("--- Refinamento Concluído ---\n")
    return consolidated_data
