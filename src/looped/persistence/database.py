from __future__ import annotations

import sqlite3
from pathlib import Path


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        schema_path = Path(__file__).resolve().parent.parent / "db" / "schema.sql"
        with self.connect() as connection:
            connection.executescript(schema_path.read_text(encoding="utf-8"))
            self._run_migrations(connection)

    @staticmethod
    def _run_migrations(connection: sqlite3.Connection) -> None:
        clip_columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(clips)").fetchall()
        }
        if "hotkey" not in clip_columns:
            connection.execute("ALTER TABLE clips ADD COLUMN hotkey TEXT DEFAULT NULL")

        playlist_tables = {
            str(row["name"])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        if "playlist_tracks" in playlist_tables and "playlist_items" in playlist_tables:
            connection.execute(
                """
                INSERT OR IGNORE INTO playlist_items (playlist_id, item_type, item_id, position)
                SELECT playlist_id, 'track', track_id, position
                FROM playlist_tracks
                """
            )
