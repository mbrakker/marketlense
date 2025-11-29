import sqlite3
from typing import Optional, Tuple

DDL = """
CREATE TABLE IF NOT EXISTS processed (
  file_id TEXT PRIMARY KEY,
  md5 TEXT NOT NULL,
  processed_at INTEGER NOT NULL,
  openai_file_id TEXT
);
"""

class State:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.execute(DDL)
        self.conn.commit()

    def already_processed(self, file_id: str, md5: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM processed WHERE file_id=? AND md5=?", (file_id, md5)
        )
        return cur.fetchone() is not None

    def record(self, file_id: str, md5: str, openai_file_id: Optional[str]):
        self.conn.execute(
            "INSERT OR REPLACE INTO processed(file_id, md5, processed_at, openai_file_id) "
            "VALUES(?, ?, strftime('%s','now'), ?)",
            (file_id, md5, openai_file_id),
        )
        self.conn.commit()

    def get(self, file_id: str) -> Optional[Tuple[str, str, int, Optional[str]]]:
        cur = self.conn.execute(
            "SELECT file_id, md5, processed_at, openai_file_id FROM processed WHERE file_id=?", (file_id,)
        )
        return cur.fetchone()
