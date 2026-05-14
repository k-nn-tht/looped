from __future__ import annotations

from array import array
from pathlib import Path
from threading import Thread

import audioread
from PySide6.QtCore import QObject, Signal


class WaveformService(QObject):
    waveform_ready = Signal(str, list, str)

    def __init__(self) -> None:
        super().__init__()
        self._cache: dict[tuple[str, int], list[float]] = {}

    def request_waveform(self, filepath: str, target_points: int = 512) -> None:
        cache_key = (filepath, target_points)
        if cache_key in self._cache:
            self.waveform_ready.emit(filepath, self._cache[cache_key], "")
            return

        worker = Thread(
            target=self._load_waveform,
            args=(filepath, target_points),
            daemon=True,
        )
        worker.start()

    def _load_waveform(self, filepath: str, target_points: int) -> None:
        try:
            waveform = self._extract_waveform(filepath, target_points)
            self._cache[(filepath, target_points)] = waveform
            self.waveform_ready.emit(filepath, waveform, "")
        except Exception as exc:
            self.waveform_ready.emit(filepath, [], str(exc))

    @staticmethod
    def _extract_waveform(filepath: str, target_points: int) -> list[float]:
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError("Track file is missing from disk.")

        raw_peaks: list[float] = []
        frames_per_bucket = 2048

        with audioread.audio_open(str(path)) as audio_file:
            channels = max(1, int(getattr(audio_file, "channels", 1) or 1))
            peak = 0.0
            frame_count = 0

            for chunk in audio_file:
                samples = array("h")
                samples.frombytes(chunk)
                if not samples:
                    continue

                channel_count = channels
                usable_length = len(samples) - (len(samples) % channel_count)
                for index in range(0, usable_length, channel_count):
                    amplitude = 0
                    for channel_offset in range(channel_count):
                        amplitude = max(amplitude, abs(samples[index + channel_offset]))
                    peak = max(peak, amplitude / 32768.0)
                    frame_count += 1

                    if frame_count >= frames_per_bucket:
                        raw_peaks.append(peak)
                        peak = 0.0
                        frame_count = 0

            if frame_count or not raw_peaks:
                raw_peaks.append(peak)

        if len(raw_peaks) >= target_points:
            bucket_width = len(raw_peaks) / target_points
            return [
                max(raw_peaks[int(index * bucket_width) : max(int((index + 1) * bucket_width), int(index * bucket_width) + 1)])
                for index in range(target_points)
            ]

        if not raw_peaks:
            return [0.0] * target_points

        padded = list(raw_peaks)
        while len(padded) < target_points:
            padded.append(raw_peaks[min(len(raw_peaks) - 1, len(padded) * len(raw_peaks) // target_points)])
        return padded[:target_points]
