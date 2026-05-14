from __future__ import annotations

from looped.audio.backends.base import CaptureBackend, RoutingBackend


class BlackHoleCaptureBackend(CaptureBackend):
    def start_capture(self) -> None:
        raise NotImplementedError("TODO: implement BlackHole/Core Audio capture on macOS.")

    def stop_capture(self) -> None:
        raise NotImplementedError("TODO: implement BlackHole/Core Audio capture on macOS.")


class WasapiLoopbackCaptureBackend(CaptureBackend):
    def start_capture(self) -> None:
        raise NotImplementedError("TODO: implement WASAPI loopback capture on Windows.")

    def stop_capture(self) -> None:
        raise NotImplementedError("TODO: implement WASAPI loopback capture on Windows.")


class VirtualOutputRoutingBackend(RoutingBackend):
    def route_to_virtual_output(self, enabled: bool) -> None:
        raise NotImplementedError("TODO: implement virtual audio output routing.")
