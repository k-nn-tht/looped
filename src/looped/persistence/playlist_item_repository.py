from __future__ import annotations

from looped.domain.models import Clip, Track
from looped.persistence.database import Database
from looped.persistence.repositories import ClipRepository, TrackRepository


class PlaylistItemRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def add_item(self, playlist_id: int, item_type: str, item_id: int) -> bool:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(MAX(position), -1) AS max_position
                FROM playlist_items
                WHERE playlist_id = ? AND item_type = ?
                """,
                (playlist_id, item_type),
            ).fetchone()
            next_position = int(row["max_position"]) + 1
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO playlist_items (playlist_id, item_type, item_id, position)
                VALUES (?, ?, ?, ?)
                """,
                (playlist_id, item_type, item_id, next_position),
            )
            return bool(cursor.rowcount)

    def remove_item(self, playlist_id: int, item_type: str, item_id: int) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                DELETE FROM playlist_items
                WHERE playlist_id = ? AND item_type = ? AND item_id = ?
                """,
                (playlist_id, item_type, item_id),
            )

    def get_tracks_for_playlist(self, playlist_id: int) -> list[Track]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT t.id, t.filepath, t.title, t.artist, t.album, t.duration_ms, t.imported_at
                FROM playlist_items pi
                INNER JOIN tracks t ON t.id = pi.item_id
                WHERE pi.playlist_id = ? AND pi.item_type = 'track'
                ORDER BY pi.position ASC, t.title COLLATE NOCASE, t.artist COLLATE NOCASE
                """,
                (playlist_id,),
            ).fetchall()
        return [TrackRepository._row_to_track(row) for row in rows]

    def get_clips_for_playlist(self, playlist_id: int) -> list[Clip]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT c.id, c.source_track_id, c.title, c.start_ms, c.end_ms, c.tags, c.hotkey, c.created_at
                FROM playlist_items pi
                INNER JOIN clips c ON c.id = pi.item_id
                WHERE pi.playlist_id = ? AND pi.item_type = 'clip'
                ORDER BY pi.position ASC, c.created_at DESC
                """,
                (playlist_id,),
            ).fetchall()
        return [ClipRepository._row_to_clip(row) for row in rows]
