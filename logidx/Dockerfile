FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN useradd --create-home --uid 10001 logidx
COPY pyproject.toml README.md alembic.ini ./
COPY src ./src
RUN pip install .
COPY config ./config
ENV LOGIDX_CONFIG_DIR=/app/config LOGIDX_DATA_DIR=/data
RUN mkdir -p /data && chown logidx:logidx /data
USER logidx
EXPOSE 8780
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8780/healthz')"
CMD ["sh", "-c", "logidx initdb && logidx serve --host 0.0.0.0 --port 8780"]
