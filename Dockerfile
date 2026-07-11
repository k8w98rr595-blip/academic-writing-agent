FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    HOST=0.0.0.0 \
    PORT=8000 \
    OBJECT_STORAGE_DIR=/data/objects

WORKDIR /app
RUN addgroup --system paperlight \
    && adduser --system --ingroup paperlight paperlight \
    && apt-get update \
    && apt-get install --yes --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*
COPY services/api/requirements.txt /app/services/api/requirements.txt
RUN pip install --no-cache-dir -r /app/services/api/requirements.txt
COPY services /app/services
COPY infra/docker-entrypoint.sh /usr/local/bin/paperlight-entrypoint
RUN chmod 0755 /usr/local/bin/paperlight-entrypoint \
    && mkdir -p /data/objects \
    && chown -R paperlight:paperlight /app /data

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:' + __import__('os').environ.get('PORT','8000') + '/api/health', timeout=3)"
ENTRYPOINT ["paperlight-entrypoint"]
CMD ["sh", "-c", "python -m uvicorn services.api.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
