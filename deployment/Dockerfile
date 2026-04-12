FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git openssh-client ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev

COPY . .

ENV PYTHONUNBUFFERED=1
ENV TZ=America/Sao_Paulo

CMD ["uv", "run", "python", "main.py"]
