FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
# Install torch CPU-only first to prevent pip from resolving the CUDA variant (~3 GB)
RUN pip install --no-cache-dir torch --extra-index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt
# Pre-download the embedding model so the first pod start is instant
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY app/ .

ENV NEWS_DB_PATH=/data/news.db
# Long-running process: listens for commands and self-schedules the digest.
ENTRYPOINT ["python", "main.py"]
