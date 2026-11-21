"""Application imports no longer perform implicit Phase 1 schema upgrades.
Migration compatibility and data preservation are exercised in test_migrations.py.
"""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def test_import_preserves_partial_legacy_schema_without_implicit_ddl(tmp_path):
    path=tmp_path/'legacy.db'
    with sqlite3.connect(path) as db:
        db.execute('''CREATE TABLE journals (
            id INTEGER PRIMARY KEY, title VARCHAR(200) NOT NULL, content TEXT NOT NULL,
            created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
        )''')
        db.execute("INSERT INTO journals VALUES (1,'旧日记','保留原正文','2025-12-31 20:00:00','2025-12-31 20:00:00')")
        original=db.execute('SELECT * FROM journals').fetchall()
        columns=db.execute('PRAGMA table_info(journals)').fetchall()
    env={**os.environ,'DATABASE_URL':'sqlite:///'+str(path),'MEDIA_DIR':str(tmp_path/'media'),
         'PYTHONPATH':str(Path(__file__).parents[1]/'backend')}
    for _ in range(2):
        subprocess.run([sys.executable,'-c','import app.main'],env=env,check=True,capture_output=True)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT * FROM journals').fetchall()==original
        assert db.execute('PRAGMA table_info(journals)').fetchall()==columns
        assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()==[('journals',)]
