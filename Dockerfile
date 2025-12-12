# ============== FASE 1: BUILDER (Instala dependências Python) ==============
# Usar uma imagem completa para o build
FROM python:3.11 AS builder

# Configura o diretório de trabalho
WORKDIR /app

# É necessário instalar as dependências de sistema (apt-get) para que o pip funcione corretamente
# com certas bibliotecas, embora o foco da instalação seja no final.
# Instalar aqui é redundante, mas é uma boa prática para garantir o build completo.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copia o arquivo de requisitos e instala os pacotes Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ================ FASE 2: EXECUÇÃO (Runtime) ================
# Usar uma imagem slim para manter o container leve.
FROM python:3.11-slim as final

# Configura o diretório de trabalho
WORKDIR /app

# --- CORREÇÃO CRUCIAL (1): Instalação do Tesseract-OCR Binário ---
# Esta etapa garante que os binários do tesseract e poppler-utils (para PDF)
# estejam disponíveis no sistema operacional Linux do container final.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        poppler-utils \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-por \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# --- CORREÇÃO CRUCIAL (2): Copia os Pacotes Python ---
# Isso move o pytesseract e todas as outras dependências do estágio 'builder'
# para o estágio 'final'.
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Copia o código da sua aplicação (o Coolify fará isso sem o .env)
COPY ./app /app/app

# Define o comando de execução
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
