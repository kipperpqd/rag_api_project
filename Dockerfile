# rag_api_project/Dockerfile (Versão final para desenvolvimento)

# --- FASE 1: Builder (Instalação de Dependências de Sistema) ---
FROM python:3.11-slim as builder

WORKDIR /app

# 1. Instalação de Ferramentas e Dependências de OCR/PDF
# Incluímos o Tesseract e as bibliotecas de linguagem (eng/por) para OCR.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        # Dependências do Poppler (para pdf2image)
        poppler-utils \
        # Tesseract e dados de linguagem para OCR
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-por \
        # Ferramentas básicas para compilação
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. Copia os requisitos e instala as bibliotecas Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# --- FASE 2: Runtime (Container Final de Execução) ---
FROM python:3.11-slim

# Re-instala as dependências de sistema no container final
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        poppler-utils \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-por \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia as dependências Python instaladas na FASE 1
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copia o código da sua aplicação
COPY ./app /app/app

EXPOSE 8000

# Define o comando de inicialização
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
