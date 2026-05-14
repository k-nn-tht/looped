from __future__ import annotations

from datetime import datetime
from typing import Iterable

from looped.domain.models import Clip, Playlist, Track
from looped.persistence.database import Database


def _to_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


class TrackRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def upsert(self, track: Track) -> int:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO tracks (filepath, title, artist, album, duration_ms, imported_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(filepath) DO UPDATE SET
                    title = excluded.title,
                    artist = excluded.artist,
                    album = excluded.album,
                    duration_ms = excluded.duration_ms
                """,
                (
                    track.filepath,
                    track.title,
                    track.artist,
                    track.album,
                    track.duration_ms,
                    track.imported_at.isoformat(),
                ),
            )
            row = connection.execute(
                "SELECT id FROM tracks WHERE filepath = ?",
                (track.filepath,),
            ).fetchone()
            return int(row["id"])

    def list_all(self) -> list[Track]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, filepath, title, artist, album, duration_ms, imported_at
                FROM tracks
                ORDER BY title COLLATE NOCASE, artist COLLATE NOCASE
                """
            ).fetchall()
        return [self._row_to_track(row) for row in rows]

    def list_for_playlist(self, playlist_id: int) -> list[Track]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT t.id, t.filepath, t.title, t.artist, t.album, t.duration_ms, t.imported_at
                FROM tracks t
                INNER JOIN playlist_tracks pt ON pt.track_id = t.id
                WHERE pt.playlist_id = ?
                ORDER BY pt.position ASC, t.title COLLATE NOCASE, t.artist COLLATE NOCASE
                """,
                (playlist_id,),
            ).fetchall()
        return [self._row_to_track(row) for row in rows]

    def get(self, track_id: int) -> Track | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT id, filepath, title, artist, album, duration_ms, imported_at
                FROM tracks
                WHERE id = ?
                """,
                (track_id,),
            ).fetchone()
        return self._row_to_track(row) if row else None

    def delete(self, track_id: int) -> None:
        with self.database.connect() as connection:
            connection.execute("DELETE FROM tracks WHERE id = ?", (track_id,))

    def list_by_ids(self, track_ids: Iterable[int]) -> list[Track]:
        ids = list(track_ids)
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT id, filepath, title, artist, album, duration_ms, imported_at
                FROM tracks
                WHERE id IN ({placeholders})
                """,
                ids,
            ).fetchall()
        return [self._row_to_track(row) for row in rows]

    @staticmethod
    def _row_to_track(row) -> Track:
        return Track(
            id=int(row["id"]),
            filepath=str(row["filepath"]),
            title=str(row["title"]),
            artist=str(row["artist"]),
            album=str(row["album"]),
            duration_ms=int(row["duration_ms"]),
            imported_at=_to_datetime(str(row["imported_at"])),
        )


class ClipRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, clip: Clip) -> int:
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO clips (source_track_id, title, start_ms, end_ms, tags, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    clip.source_track_id,
                    clip.title,
                    clip.start_ms,
                    clip.end_ms,
                    clip.tags,
                    clip.created_at.isoformat(),
                ),
            )
            return int(cursor.lastrowid)

    def list_all(self) -> list[Clip]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, source_track_id, title, start_ms, end_ms, tags, created_at
                FROM clips
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [self._row_to_clip(row) for row in rows]

    def get(self, clip_id: int) -> Clip | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT id, source_track_id, title, start_ms, end_ms, tags, created_at
                FROM clips
                WHERE id = ?
                """,
                (clip_id,),
            ).fetchone()
        return self._row_to_clip(row) if row else None

    def delete(self, clip_id: int) -> None:
        with self.database.connect() as connection:
            connection.execute("DELETE FROM clips WHERE id = ?", (clip_id,))

    @staticmethod
    def _row_to_clip(row) -> Clip:
        return Clip(
            id=int(row["id"]),
            source_track_id=int(row["source_track_id"]),
            title=str(row["title"]),
            start_ms=int(row["start_ms"]),
            end_ms=int(row["end_ms"]),
            tags=str(row["tags"]),
            created_at=_to_datetime(str(row["created_at"])),
        )


class PlaylistRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, name: str, created_at: datetime) -> int:
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO playlists (name, created_at)
                VALUES (?, ?)
                """,
                (name, created_at.isoformat()),
            )
            return int(cursor.lastrowid)

    def list_all(self) -> list[Playlist]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, created_at
                FROM playlists
                ORDER BY name COLLATE NOCASE
                """
            ).fetchall()
        return [self._row_to_playlist(row) for row in rows]

    def get(self, playlist_id: int) -> Playlist | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT id, name, created_at
                FROM playlists
                WHERE id = ?
                """,
                (playlist_id,),
            ).fetchone()
        return self._row_to_playlist(row) if row else None

    def add_tracks(self, playlist_id: int, track_ids: Iterable[int]) -> int:
        ids = list(dict.fromkeys(track_ids))
        if not ids:
            return 0

        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(position), -1) AS max_position FROM playlist_tracks WHERE playlist_id = ?",
                (playlist_id,),
            ).fetchone()
            next_position = int(row["max_position"]) + 1
            inserted = 0

            for track_id in ids:
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO playlist_tracks (playlist_id, track_id, position)
                    VALUES (?, ?, ?)
                    """,
                    (playlist_id, track_id, next_position),
                )
                if cursor.rowcount:
                    inserted += 1
                    next_position += 1

            return inserted

    @staticmethod
    def _row_to_playlist(row) -> Playlist:
        return Playlist(
            id=int(row["id"]),
            name=str(row["name"]),
            created_at=_to_datetime(str(row["created_at"])),
        )
