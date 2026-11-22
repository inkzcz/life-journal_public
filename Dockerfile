# One immutable business image, three isolated role containers. No image push.
FROM node:22-alpine@sha256:12f54cafa58d0e96554ae05871e29663ff7241836377dc9a7916449b8adb062c AS frontend-build
WORKDIR /src
COPY frontend/package*.json ./
RUN --mount=type=secret,id=build_ca \
    if [ -f /run/secrets/build_ca ]; then NODE_EXTRA_CA_CERTS=/run/secrets/build_ca npm ci; else npm ci; fi
COPY frontend/ ./
ARG BUILD_INFO={}
RUN LJ_BUILD_INFO="$BUILD_INFO" npm run build

FROM caddy:2-alpine@sha256:fc9cbc100585871d18d4e451cca7021785c90a7006087427ae5ceb3e4efe6424 AS caddy-runtime

# PostgreSQL 17 binaries support backup and isolated restore/trial migration.
# Install packages directly: never resolve or pull a PostgreSQL container image.
FROM python:3.12-slim-bookworm@sha256:0f086103b026048cc50cb5da25ec435c023c5241a83fc44daea593377abc61c4 AS runtime-base
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
FROM runtime-base AS python-build
COPY backend/requirements.txt backend/constraints-release.txt ./
RUN --mount=type=secret,id=build_ca \
    set -eu; \
    if [ -f /run/secrets/build_ca ]; then export PIP_CERT=/run/secrets/build_ca; \
      printf 'Acquire::https::CaInfo "/run/secrets/build_ca";\n' > /etc/apt/apt.conf.d/99build-ca; fi; \
    apt-get update; \
    libpq_version="$(dpkg-query -W -f='${Version}' libpq5)"; \
    apt-get install -y --no-install-recommends gcc libc6-dev "libpq-dev=$libpq_version"; \
    pip install --no-cache-dir --no-binary=psycopg-c --report=/python-install-report.json -c constraints-release.txt -r requirements.txt; \
    python -c 'import psycopg; assert psycopg.pq.__impl__ == "c"'; \
    gcc --version > /compiler-version.txt; pg_config --configure > /libpq-configure.txt

FROM runtime-base AS business
COPY --from=python-build /opt/venv /opt/venv
COPY --from=python-build /python-install-report.json /usr/share/doc/life-journal/python-install-report.json
COPY --from=python-build /compiler-version.txt /libpq-configure.txt /usr/share/doc/life-journal/
COPY backend/requirements.txt backend/constraints-release.txt ./
COPY backend/app ./app
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY --from=frontend-build /src/dist /srv
COPY --from=caddy-runtime /usr/bin/caddy /usr/bin/caddy
COPY frontend/Caddyfile /etc/caddy/Caddyfile
COPY LICENSE COPYRIGHT.md /usr/share/doc/life-journal/
COPY third_party/BINARY_NOTICE.md third_party/LGPL_REPLACEMENT.md third_party/SOURCE_BUILD.md third_party/notice-index.json /usr/share/doc/life-journal/
COPY third_party/licenses /usr/share/doc/life-journal/licenses
COPY scripts/binary_notices.py scripts/license_evidence.py /tmp/legal-tools/
# Browser recipients receive actual bundled-package notices plus original/icon
# grants. This reference catalogue is not a substitute for corresponding source.
RUN python /tmp/legal-tools/binary_notices.py \
    && cp -R /usr/share/doc/life-journal/. /srv/legal/ \
    && rm -r /tmp/legal-tools
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
