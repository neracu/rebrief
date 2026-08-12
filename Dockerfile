FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md LICENSE MANIFEST.in ./
COPY rebrief ./rebrief

RUN pip install --no-cache-dir ".[web,tokens]"

ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT', '8000'))"

CMD ["sh", "-c", "uvicorn rebrief.webapp.app:app --host 0.0.0.0 --port ${PORT}"]
