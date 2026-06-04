FROM python:3.11-slim

# Install system dependencies including Tesseract OCR and WeasyPrint
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    libtesseract-dev \
    poppler-utils \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
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
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ARG DOWNLOAD_EMBEDDING_MODEL=true
ARG EMBEDDING_MODEL_NAME=all-MiniLM-L6-v2
ENV EMBEDDING_MODEL_PATH=/app/models/all-MiniLM-L6-v2
RUN if [ "$DOWNLOAD_EMBEDDING_MODEL" = "true" ]; then \
      python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('$EMBEDDING_MODEL_NAME').save('$EMBEDDING_MODEL_PATH')" ; \
    fi

# Copy application code
COPY . .

# Create directory for ChromaDB persistence
RUN mkdir -p /app/chroma_db

ENV EMBEDDING_OFFLINE=true
ENV TRANSFORMERS_OFFLINE=1
ENV HF_HUB_OFFLINE=1

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
