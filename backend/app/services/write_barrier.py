"""A database-scoped session lock spans DB commits AND media filesystem writes.
Shared API/CLI writers coexist. A backup holds the exclusive lock until both
pg_dump and the media copy finish. Disconnect/crash releases the lock in PG.
"""
from contextlib import contextmanager
from sqlalchemy import text
from fastapi import HTTPException
KEY=721934003

@contextmanager
def writer(bind):
    if bind.dialect.name!='postgresql':yield;return
    with bind.connect().execution_options(isolation_level='AUTOCOMMIT') as con:
        if not con.scalar(text(f'SELECT pg_try_advisory_lock_shared({KEY})')):
            raise HTTPException(503,'正在进行数据维护或一致性备份，暂时不能保存；输入仍保留，请稍后重试',headers={'Retry-After':'30'})
        try:yield
        finally:con.scalar(text(f'SELECT pg_advisory_unlock_shared({KEY})'))

@contextmanager
def frozen(bind):
    if bind.dialect.name!='postgresql':raise RuntimeError('一致性备份仅支持 PostgreSQL')
    with bind.connect().execution_options(isolation_level='AUTOCOMMIT') as con:
        con.execute(text("SET lock_timeout='30s'"))
        con.scalar(text(f'SELECT pg_advisory_lock({KEY})'))
        try:yield con
        finally:con.scalar(text(f'SELECT pg_advisory_unlock({KEY})'))
