# ============== FASE 1: BUILDER (Instala dependências Python) ==============
FROM python:3.11 AS builder

WORKDIR /app

# Instalar dependências de sistema para o pip (libpq-dev para psycopg2)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copia o arquivo de requisitos e instala os pacotes Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ================ FASE 2: EXECUÇÃO (Runtime) ================
FROM python:3.11-slim as final

WORKDIR /app

# --- CORREÇÃO CRUCIAL (1): Instalação do Tesseract-OCR Binário ---
# Esta etapa é para o Tesseract-OCR, o binário que o pytesseract PRECISA.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        poppler-utils \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-por \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*
    
# --- CORREÇÃO FINAL (2): Copia o ambiente Python completo ---
# Isso resolve o "ModuleNotFoundError: No module named 'pytesseract'"
# E também o erro anterior de "uvicorn: executable file not found".
COPY --from=builder /usr/local /usr/local

# Copia o código da sua aplicação
COPY ./app /app/app

# Define o comando de execução
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
