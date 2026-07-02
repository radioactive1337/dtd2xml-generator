# syntax=docker/dockerfile:1

FROM node:20-alpine AS frontend-builder

WORKDIR /build/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim AS runtime

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libxml2 \
        libxslt1.1 \
        libnsl2 \
        unzip \
    && (apt-get install -y --no-install-recommends libaio1 || apt-get install -y --no-install-recommends libaio1t64) \
    && set -eux; \
       libaio_path="$(ldconfig -p | awk '/libaio\.so/{print $NF; exit}')" || true; \
       if [ -n "${libaio_path:-}" ]; then \
           mkdir -p /usr/lib/x86_64-linux-gnu /lib/x86_64-linux-gnu; \
           ln -sf "$libaio_path" /usr/lib/x86_64-linux-gnu/libaio.so.1; \
           ln -sf "$libaio_path" /lib/x86_64-linux-gnu/libaio.so.1; \
       fi \
    && ldconfig \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend/ /app/backend/
COPY --from=frontend-builder /build/frontend/dist /app/frontend/dist
COPY config/connections.json.example /app/config/connections.json.example
COPY docker/entrypoint.sh /app/docker/entrypoint.sh
COPY docker/oracle/ /tmp/oracle/

RUN mkdir -p /app/dtd_schemas /app/mapping_presets /app/presets /app/config \
    && if ls /tmp/oracle/instantclient-basic-linux.x64-*.zip >/dev/null 2>&1; then \
        mkdir -p /opt/oracle \
        && unzip -q /tmp/oracle/instantclient-basic-linux.x64-*.zip -d /opt/oracle \
        && ln -sfn "$(find /opt/oracle -maxdepth 1 -type d -name 'instantclient_*' | head -n 1)" /opt/oracle/instantclient; \
       else \
        echo "Oracle Instant Client zip not found in docker/oracle/. Skipping Oracle client install."; \
       fi \
    && rm -rf /tmp/oracle \
    && sed -i 's/\r$//' /app/docker/entrypoint.sh \
    && chmod +x /app/docker/entrypoint.sh

WORKDIR /app/backend

ENV PYTHONUNBUFFERED=1
ENV LD_LIBRARY_PATH=/opt/oracle/instantclient:${LD_LIBRARY_PATH}

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health')" || exit 1

CMD ["/bin/sh", "/app/docker/entrypoint.sh"]
