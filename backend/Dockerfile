FROM python:3.12-slim
WORKDIR /app
ARG BUILD_INFO={}
RUN BUILD_INFO="$BUILD_INFO" python -c 'import os,json;from pathlib import Path;Path("/app/BUILD_INFO.json").write_text(json.dumps(json.loads(os.environ["BUILD_INFO"])));Path("/app/BUILD_INFO.json").chmod(0o444)'
ARG APP_VERSION=unversioned
ENV LIFE_JOURNAL_VERSION=$APP_VERSION
RUN printf '%s\n' "$APP_VERSION" > /app/BUILD_VERSION
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN --mount=type=secret,id=build_ca \
    if [ -f /run/secrets/build_ca ]; then PIP_CERT=/run/secrets/build_ca pip install --no-cache-dir -r requirements.txt; else pip install --no-cache-dir -r requirements.txt; fi
COPY app ./app
COPY alembic.ini .
COPY alembic ./alembic
RUN useradd -u 10001 -m appuser && mkdir -p /data/media && chown -R appuser:appuser /data /app && chown root:root /app/BUILD_INFO.json && chmod 0444 /app/BUILD_INFO.json
ENV CONTAINER_ROLE=api
USER root
ENTRYPOINT ["python", "-m", "app.container_entrypoint"]
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-access-log"]
