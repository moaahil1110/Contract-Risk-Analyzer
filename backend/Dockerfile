FROM python:3.11-slim

# Install system dependencies including Tesseract OCR and WeasyPrint
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    libtesseract-dev \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ARG DOWNLOAD_EMBEDDING_MODEL=false
ARG EMBEDDING_MODEL_NAME=all-MiniLM-L6-v2
ARG EMBEDDING_MODEL_PATH=/app/models/all-MiniLM-L6-v2
RUN if [ "$DOWNLOAD_EMBEDDING_MODEL" = "true" ]; then \
      python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('$EMBEDDING_MODEL_NAME').save('$EMBEDDING_MODEL_PATH')" ; \
    fi

# Copy application code
COPY backend/ .

# Create directory for ChromaDB persistence
RUN mkdir -p /app/chroma_db && chmod +x /app/start_railway.sh

ENV EMBEDDING_MODEL=all-MiniLM-L6-v2
ENV EMBEDDING_OFFLINE=false
ENV RAG_EAGER_INIT=false

# Expose port
EXPOSE 8000

# Run the web server and, by default, a lightweight worker in the same Railway service.
CMD ["/app/start_railway.sh"]
