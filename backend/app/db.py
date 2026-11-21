import os
from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker, DeclarativeBase
def database_url():
    if os.environ.get('DATABASE_URL'):
        return os.environ['DATABASE_URL']
    return URL.create(
        'postgresql+psycopg', username=os.environ['POSTGRES_USER'],
        password=os.environ['POSTGRES_PASSWORD'], host=os.getenv('POSTGRES_HOST', 'db'),
        port=int(os.getenv('POSTGRES_PORT', '5432')), database=os.environ['POSTGRES_DB'],
    )

engine = create_engine(database_url(), pool_pre_ping=True, hide_parameters=True)
# SQLite is used by the local compatibility suite; enforce the declared FKs,
# including cascade rules, just as PostgreSQL does. Never alter schema on connect.
if engine.dialect.name == 'sqlite':
    @event.listens_for(engine, 'connect')
    def sqlite_integrity(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')

SessionLocal = sessionmaker(bind=engine)
class Base(DeclarativeBase): pass
