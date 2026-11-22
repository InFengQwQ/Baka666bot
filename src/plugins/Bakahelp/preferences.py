from contextlib import closing
from pathlib import Path
import sqlite3


class Preferences:
    def __init__(self, path: Path):
        self.path = path

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=5)
        db.execute('CREATE TABLE IF NOT EXISTS disabled_scopes (scope TEXT PRIMARY KEY)')
        return db

    def disabled(self, scope: str) -> bool:
        with closing(self._connect()) as db:
            return db.execute('SELECT 1 FROM disabled_scopes WHERE scope = ?', (scope,)).fetchone() is not None

    def disable(self, scope: str):
        with closing(self._connect()) as db, db:
            db.execute('INSERT OR IGNORE INTO disabled_scopes(scope) VALUES (?)', (scope,))
