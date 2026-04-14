FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git openssh-client ca-certificates gosu \
 && rm -rf /var/lib/apt/lists/*

# Non-root user — app runs as this after entrypoint fixes /data ownership
RUN useradd -m -u 1000 conexus

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev

COPY deployment/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

COPY . .
RUN chown -R conexus:conexus /app

ENV PYTHONUNBUFFERED=1
ENV TZ=America/Sao_Paulo

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uv", "run", "python", "main.py"]
