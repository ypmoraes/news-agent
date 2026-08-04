FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .

ENV NEWS_DB_PATH=/data/news.db
# Long-running process: listens for commands and self-schedules the digest.
ENTRYPOINT ["python", "main.py"]
