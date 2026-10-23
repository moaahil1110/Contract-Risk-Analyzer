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
# Embeddings run on fastembed (ONNX Runtime), so no PyTorch is installed.
# This keeps the image smaller and each process several hundred MB lighter.
RUN pip install --no-cache-dir -r requirements.txt

# Bake the ~90 MB ONNX model into the image so restarts don't re-download it.
# If the download is skipped, fastembed fetches it into the same folder at runtime.
ARG DOWNLOAD_EMBEDDING_MODEL=true
ARG EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
ENV EMBEDDING_MODEL_PATH=/app/.cache/fastembed
RUN mkdir -p "$EMBEDDING_MODEL_PATH" && \
    if [ "$DOWNLOAD_EMBEDDING_MODEL" = "true" ]; then \
      python -c "from fastembed import TextEmbedding; TextEmbedding('$EMBEDDING_MODEL_NAME', cache_dir='$EMBEDDING_MODEL_PATH')" ; \
    fi

# Copy application code
COPY backend/ .

# Create directory for ChromaDB persistence
RUN mkdir -p /app/chroma_db && chmod +x /app/start_railway.sh

ENV EMBEDDING_MODEL=all-MiniLM-L6-v2
ENV EMBEDDING_OFFLINE=false
ENV RAG_EAGER_INIT=false
ENV PYTHONUNBUFFERED=1
ENV TQDM_DISABLE=1
ENV TOKENIZERS_PARALLELISM=false
ENV EMBEDDING_THREADS=1
# Fewer glibc memory pools; lowers RAM use of multi-threaded Python processes.
ENV MALLOC_ARENA_MAX=2

# Expose port
EXPOSE 8000

# Run the web server and, by default, a lightweight worker in the same Railway service.
CMD ["/app/start_railway.sh"]
