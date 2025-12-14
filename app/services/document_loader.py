# app/services/document_loader.py
import os
from typing import List, Tuple, Dict, Any, Union
from pathlib import Path
import odf.opendocument
import odf.text
from .ocr_processor import orchestrate_pre_ocr, CONTENT_MISSING_TEXTUAL

# --- Importações de Bibliotecas de Terceiros ---
try:
    # Para extração de texto estruturado
    import pdfplumber
except ImportError:
    pdfplumber = None
    
try:
    # Para conversão de PDF em imagens (requer Poppler no Docker)
    from pdf2image import convert_from_path
    from PIL import Image # O pdf2image retorna objetos PIL Image
except ImportError:
    convert_from_path = None
    Image = None

try:
    # Para processamento de arquivos DOCX
    import docx
except ImportError:
    docx = None


# --- Tipos de Saída ---
DocumentContent = str
# ----------------------------------------------------------------------
# 1. VERIFICA SE O PDF É SCANEADO
# ----------------------------------------------------------------------
def _has_sufficient_native_text(file_path: Path) -> bool:
    """
    Verifica se o PDF possui uma quantidade mínima de texto nativo.
    Usado para decidir se o Pré-OCR deve ser acionado.
    """
    try:
        total_text_length = 0
        with pdfplumber.open(file_path) as pdf:
            # Checa apenas as primeiras páginas para performance
            pages_to_check = min(3, len(pdf.pages)) 
            
            for i in range(pages_to_check):
                page = pdf.pages[i]
                # Usa uma extração simples, sem layout, para rapidez
                text = page.extract_text(layout=False) 
                if text:
                    total_text_length += len(text.strip())

        # Limiar: Se tiver menos de 100 caracteres nas 3 primeiras páginas, assume escaneado
        MIN_CHARS_THRESHOLD = 100 
        return total_text_length >= MIN_CHARS_THRESHOLD
        
    except Exception as e:
        print(f"AVISO: Falha na detecção de texto nativo do PDF: {e}")
        # Em caso de erro, assume que é escaneado para não perder o conteúdo
        return False



# ----------------------------------------------------------------------
# 1. FUNÇÕES DE CARREGAMENTO (LOADERS)
# ----------------------------------------------------------------------

def load_pdf_file(file_path: Path) -> Tuple[List[str], List[Any]]:
    """
    Carrega um arquivo PDF a partir de um Path.
    Extrai texto (pdfplumber) e rasteriza páginas para análise de imagem (pdf2image).
    """
    if pdfplumber is None or convert_from_path is None:
        print(f"-> PDF Loader: MOCK USADO - pdfplumber e/ou pdf2image não disponíveis.")
        return [f"Conteúdo mock de PDF para {file_path.name}"], []
        
    print(f"-> PDF Loader: Processando texto e imagens de {file_path.name}")
    
    texto_por_pagina = []
    imagens_para_analise = []
    
    try:
        # 1. Pré-Verificação e OCR (se necessário)
        if not _has_sufficient_native_text(file_path):
            print(f"-> PDF Loader: Detectado PDF escaneado/sem texto suficiente. Passando para Pré-OCR...")
            
            # Chama a função de OCR que retorna o texto corrigido por página
            ocr_corrected_text_list = orchestrate_pre_ocr(file_path)
            
            if ocr_corrected_text_list:
                texto_por_pagina = ocr_corrected_text_list
                print(f"-> PDF Loader: Usando texto corrigido do Tesseract.")
            else:
                # Falha total no OCR, usa o extrator nativo (que será vazio)
                print("-> PDF Loader: Pré-OCR falhou. Tentando extração nativa (pode falhar).")
        
        
        # 2. Extração Final de Texto (Se for nativo OU se o Pré-OCR falhou/não foi acionado)
        if not texto_por_pagina:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    # Extrai o texto nativo
                    text = page.extract_text(x_tolerance=2, y_tolerance=2, layout=False)
                    
                    if text and text.strip():
                        texto_por_pagina.append(text)
                    else:
                        texto_por_pagina.append(CONTENT_MISSING_TEXTUAL)
        
        # 3. Extração de Imagens (Sempre necessária para potencial Refinamento Multimodal)
        # O refinamento multimodal ainda pode ser necessário para gráficos, mesmo em PDFs nativos.
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                # Extrai a imagem PIL para análise multimodal (requer Poppler)
                page_image = page.to_image() 
                imagens_para_analise.append(page_image.original) 

        return texto_por_pagina, imagens_para_analise
    
    except Exception as e:
        print(f"ERRO ao processar PDF {file_path.name}: {e}")
        return [f"ERRO DE PROCESSAMENTO: Falha ao ler o arquivo {file_path.name}"], []


def load_docx_file(file_path: Path) -> Tuple[List[str], List[Any]]:
    """
    Carrega um arquivo DOCX usando a biblioteca python-docx.
    Retorna o texto como uma lista de uma única string (o documento completo).
    """
    if docx is None:
        print(f"-> DOCX Loader: MOCK USADO - python-docx não disponível.")
        return [f"Conteúdo mock de DOCX para {file_path.name}"], []
        
    print(f"-> DOCX Loader: Extraindo conteúdo textual de {file_path.name}")
    
    try:
        document = docx.Document(file_path)
        
        full_text = []
        for paragraph in document.paragraphs:
            if paragraph.text.strip():
                full_text.append(paragraph.text)
        
        # Retorna o texto concatenado como uma única string na lista.
        texto_completo = ["\n".join(full_text)]
        
        return texto_completo, [] 
        
    except Exception as e:
        print(f"ERRO ao processar DOCX {file_path.name}: {e}")
        return [f"ERRO DE PROCESSAMENTO DOCX: Falha ao ler o arquivo {file_path.name}"], []


def load_txt_file(file_path: Path) -> Tuple[List[str], List[Any]]:
    """
    Carrega um arquivo TXT simples.
    """
    print(f"-> TXT Loader: Carregando texto simples de {file_path.name}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            # Retorna o texto completo do arquivo em uma única string na lista
            texto_completo = [f.read()]
    except Exception as e:
        print(f"Erro ao ler TXT: {e}")
        texto_completo = [f"Erro ao carregar TXT de {file_path.name}"]
        
    return texto_completo, []

def load_odt_file(file_path: Path) -> Tuple[List[str], List[Any]]:
    """
    Carrega um arquivo ODT (OpenDocument Text) e extrai o conteúdo textual.
    """
    if odf.opendocument is None:
        print(f"-> ODT Loader: MOCK USADO - odfpy não disponível.")
        return [f"Conteúdo mock de ODT para {file_path.name}"], []
        
    print(f"-> ODT Loader: Extraindo conteúdo textual de {file_path.name}")
    
    full_text = []
    
    try:
        # Abre o arquivo ODT
        doc = odf.opendocument.load(file_path)
        
        # Itera sobre todos os elementos <text:p> (parágrafos) no corpo do documento
        for element in doc.getElementsByType(odf.text.P):
            text_content = str(element)
            if text_content.strip():
                full_text.append(text_content)

        # Retorna o texto concatenado como uma única string na lista (similar ao DOCX)
        texto_completo = ["\n".join(full_text)]
        
        return texto_completo, []
        
    except Exception as e:
        print(f"ERRO ao processar ODT {file_path.name}: {e}")
        return [f"ERRO DE PROCESSAMENTO ODT: Falha ao ler o arquivo {file_path.name}"], []



# ----------------------------------------------------------------------
# MAPA E ORQUESTRAÇÃO
# ----------------------------------------------------------------------

LOADER_MAPPING = {
    ".pdf": load_pdf_file,
    ".docx": load_docx_file,
    ".txt": load_txt_file,
    ".odt": load_odt_file,
    # Adicionar outros formatos aqui (ex: .pptx, .xlsx)
}


# ----------------------------------------------------------------------
# FUNÇÃO CENTRAL DE DESPACHO
# ----------------------------------------------------------------------

async def handle_document_load_from_path(
    file_path: Path, 
    original_filename: str
) -> Tuple[str, List[Any], str]:
    """
    Despacha o carregamento do documento para a função correta com base na 
    extensão do nome do arquivo original.

    Args:
        file_path: O caminho REAL do arquivo baixado (Path object, ex: /tmp/tmpXYZ/documento.pdf).
        original_filename: O nome do arquivo como estava no Drive (str, ex: 'Documento.gdoc').

    Returns:
        O conteúdo extraído (DocumentContent).
    """
    # 1. Obter a extensão LÓGICA do arquivo original
    file_extension = Path(original_filename).suffix.lower()
    
    # --- NOVO TRATAMENTO PARA ARQUIVOS NATIVOS SEM EXTENSÃO NO NOME ---
    if not file_extension:
        # Se o nome original não tem extensão (ex: "Documento"), mas o arquivo foi baixado/exportado
        # como PDF (o que acontece com Google Docs/Sheets/Slides), usamos o sufixo do arquivo REAL.
        # Ex: original_filename="Documento", file_path="/tmp/doc.pdf"
        
        real_extension = file_path.suffix.lower()
        print(f"DEBUG Loader: Extensão lógica ausente ('{original_filename}'). Usando extensão real de download: '{real_extension}'")
        file_extension = real_extension

    print(f"DEBUG Loader: Arquivo original: '{original_filename}'. Extensão detectada: '{file_extension}'")

    if not file_extension or file_extension not in LOADER_MAPPING:
        # Se for um formato sem loader definido (ou extensões estranhas do Drive)
        raise ValueError(f"Formato de arquivo não suportado para ingestão: {original_filename} (Extensão: {file_extension})")

    # Obtém a função de carregamento correspondente
    loader_function = LOADER_MAPPING[file_extension]
    
    try:
        # GARANTIA 2: Passa o objeto Path para os loaders internos (resolveu o AttributeError)
        document_text, document_images = loader_function(file_path)
        return document_text, document_images, file_extension
        
    except Exception as e:
        print(f"ERRO durante o carregamento do arquivo {original_filename} usando {loader_function.__name__}: {e}")
        raise
