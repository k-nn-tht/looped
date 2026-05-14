from __future__ import annotations


def format_ms(value: int) -> str:
    total_seconds = max(0, value // 1000)
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}:{seconds:02d}"
