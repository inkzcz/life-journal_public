# One immutable business image, three isolated role containers. No image push.
FROM node:22-alpine AS frontend-build
WORKDIR /src
COPY frontend/package*.json ./
RUN --mount=type=secret,id=build_ca \
    if [ -f /run/secrets/build_ca ]; then NODE_EXTRA_CA_CERTS=/run/secrets/build_ca npm ci; else npm ci; fi
COPY frontend/ ./
ARG BUILD_INFO={}
RUN LJ_BUILD_INFO="$BUILD_INFO" npm run build

FROM caddy:2-alpine AS caddy-runtime

# PostgreSQL 17 binaries support backup and isolated restore/trial migration.
# Install packages directly: never resolve or pull a PostgreSQL container image.
FROM python:3.12-slim-bookworm AS business
ENV LANG=C.UTF-8
WORKDIR /app
# PGDG supplies version 17 on Bookworm. Never create a database in this image.
# The CA bundle contains public trust roots; APT downloads run as _apt.
RUN --mount=type=secret,id=build_ca,mode=0444 \
    set -eu; \
    if [ -f /run/secrets/build_ca ]; then export CURL_CA_BUNDLE=/run/secrets/build_ca; \
      printf 'Acquire::https::CaInfo "/run/secrets/build_ca";\n' > /etc/apt/apt.conf.d/99build-ca; fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl gnupg wget; \
    curl --fail --silent --show-error https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /tmp/pgdg.asc; \
    gpg --batch --show-keys --with-colons /tmp/pgdg.asc | grep -q '^fpr:::::::::B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8:'; \
    gpg --batch --dearmor -o /usr/share/keyrings/pgdg.gpg /tmp/pgdg.asc; \
    printf 'deb [signed-by=/usr/share/keyrings/pgdg.gpg] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main\n' > /etc/apt/sources.list.d/pgdg.list; \
    printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d; chmod 755 /usr/sbin/policy-rc.d; \
    apt-get update; apt-get install -y --no-install-recommends postgresql-common; \
    printf '\ncreate_main_cluster = false\n' >> /etc/postgresql-common/createcluster.conf; \
    apt-get install -y --no-install-recommends postgresql-17 postgresql-client-17; \
    test -z "$(pg_lsclusters -h)"; \
    # postgresql-common depends on ssl-cert, whose postinst generates a key. \
    # Remove it in THIS RUN, before any layer is committed; no role uses it. \
    rm -f /etc/ssl/private/ssl-cert-snakeoil.key /etc/ssl/certs/ssl-cert-snakeoil.pem; \
    test ! -e /etc/ssl/private/ssl-cert-snakeoil.key; \
    test ! -e /etc/ssl/certs/ssl-cert-snakeoil.pem; \
    rm -f /tmp/pgdg.asc /etc/apt/apt.conf.d/99build-ca; \
    rm -rf /var/lib/apt/lists/*; \
    python -m venv /opt/venv
ENV PATH=/opt/venv/bin:/usr/lib/postgresql/17/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    XDG_CONFIG_HOME=/tmp/caddy-config XDG_DATA_HOME=/tmp/caddy-data
COPY backend/requirements.txt ./
RUN --mount=type=secret,id=build_ca \
    if [ -f /run/secrets/build_ca ]; then PIP_CERT=/run/secrets/build_ca pip install --no-cache-dir -r requirements.txt; else pip install --no-cache-dir -r requirements.txt; fi
COPY backend/app ./app
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY --from=frontend-build /src/dist /srv
COPY --from=caddy-runtime /usr/bin/caddy /usr/bin/caddy
COPY frontend/Caddyfile /etc/caddy/Caddyfile
ARG BUILD_INFO={}
ARG APP_VERSION=unversioned
ENV LIFE_JOURNAL_VERSION=$APP_VERSION
RUN BUILD_INFO="$BUILD_INFO" python -c 'import os,json;from pathlib import Path;Path("/app/BUILD_INFO.json").write_text(json.dumps(json.loads(os.environ["BUILD_INFO"])));Path("/app/BUILD_INFO.json").chmod(0o444)' \
    && printf '%s\n' "$APP_VERSION" > /app/BUILD_VERSION \
    && groupadd --gid 10001 appuser && useradd --uid 10001 --gid 10001 --create-home appuser \
    && mkdir -p /data/media && chown 10001:10001 /data/media \
    && chmod -R a+rX /app /srv /etc/caddy \
    && python -c 'import sys; assert sys.version_info[:2] == (3,12); print(sys.version)' \
    && caddy version \
    && for tool in initdb pg_ctl postgres pg_dump pg_restore; do "$tool" --version | grep ' 17\.'; done
# Initial empty bind-directory preparation only; container_entrypoint then drops
# UID/GID permanently. The web role never touches media or backups.
USER root
ENTRYPOINT ["python", "-m", "app.unified_entrypoint"]
CMD ["api"]
