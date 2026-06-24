FROM python:3.12-slim

# Install rclone + bash + curl
RUN apt-get update && \
    apt-get install -y --no-install-recommends bash curl unzip ca-certificates && \
    curl -fsSL https://rclone.org/install.sh | bash && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/ ./bot/
COPY scripts/ ./scripts/
RUN chmod +x ./scripts/organize.sh

# Persisted data (rclone.conf, logs)
RUN mkdir -p /data
ENV RCLONE_CONF_PATH=/data/rclone.conf
ENV PORT=8080

EXPOSE 8080

# Health check for Koyeb / Docker
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:${PORT}/health || exit 1

CMD ["python", "-m", "bot.main"]
