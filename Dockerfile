# syntax=docker/dockerfile:1

FROM node:20-alpine AS frontend-builder

WORKDIR /build/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci

ENV NODE_ENV=production
COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim AS runtime

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libxml2 \
        libxslt1.1 \
        libaio1t64 \
        libnsl2 \
        unzip \
    && if [ -e /usr/lib/x86_64-linux-gnu/libaio.so.1t64 ] && [ ! -e /usr/lib/x86_64-linux-gnu/libaio.so.1 ]; then \
        ln -s /usr/lib/x86_64-linux-gnu/libaio.so.1t64 /usr/lib/x86_64-linux-gnu/libaio.so.1; \
       fi \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app \
    && useradd --system --gid app --home /app --shell /usr/sbin/nologin app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend/ /app/backend/
COPY --from=frontend-builder /build/frontend/dist /app/frontend/dist
COPY config/connections.json.example /app/config/connections.json.example
COPY docker/entrypoint.sh /app/docker/entrypoint.sh
COPY docker/oracle/ /tmp/oracle/

RUN mkdir -p /app/dtd_schemas /app/mapping_presets /app/presets /app/config \
    && if ls /tmp/oracle/instantclient-basic-linux.x64-*.zip >/dev/null 2>&1; then \
        mkdir -p /opt/oracle \
        && unzip -q /tmp/oracle/instantclient-basic-linux.x64-*.zip -d /opt/oracle \
        && ln -sfn "$(find /opt/oracle -maxdepth 1 -type d -name 'instantclient_*' | head -n 1)" /opt/oracle/instantclient \
        && ls /opt/oracle/instantclient/libclntsh.so* >/dev/null 2>&1 \
        && chmod -R a+rX /opt/oracle; \
       else \
        echo "Oracle Instant Client zip not found in docker/oracle/. Skipping Oracle client install."; \
       fi \
    && rm -rf /tmp/oracle \
    && sed -i 's/\r$//' /app/docker/entrypoint.sh \
    && chmod +x /app/docker/entrypoint.sh \
    && chown -R app:app /app

WORKDIR /app/backend

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LD_LIBRARY_PATH=/opt/oracle/instantclient

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health')" || exit 1

USER app

CMD ["/bin/sh", "/app/docker/entrypoint.sh"]
