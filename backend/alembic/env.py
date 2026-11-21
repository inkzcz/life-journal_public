# Alembic template scaffolding adapted under MIT; Copyright 2009-2026 Michael Bayer.
# See third_party/SOURCE_REVIEW.md (A001); project-specific migration policy is original.
from alembic import context
from sqlalchemy import text
from app.db import engine
from app.models import Base
from app.calendar import models as calendar_models
from app.exchange import models as exchange_models
from app import album_models, experience_models, v5_models, tag_models, recovery_models, life_models, template_models, blog_models, archive_models, content_models

config = context.config


def run(connection):
    if connection.dialect.name == 'postgresql':
        connection.execute(text("SET LOCAL lock_timeout = '10s'"))
        connection.execute(text("SET LOCAL statement_timeout = '120s'"))
        connection.execute(text('SELECT pg_advisory_xact_lock(7820143301)'))
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError('本迁移需要只读核对实际旧表，不支持离线 SQL 或盲目 stamp')
connection = config.attributes.get('connection')
if connection is not None:
    run(connection)
else:
    with engine.begin() as connection:
        run(connection)
