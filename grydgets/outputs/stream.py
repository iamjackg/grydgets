"""In-memory frame stream for remote displays.

Keeps the latest encoded frame and the set of subscribers waiting to be told
it changed. The HTTP endpoints that serve them live in ``cli.py``, because
Flask routes cannot be unregistered and SIGUSR1 recreates every output -- an
output that registered its own routes would fail on the second reload.
"""

from __future__ import annotations

import hashlib
import io
import queue
import threading
import time
from typing import Any

import pygame

from grydgets.outputs import Output, register_output

# stop() pushes this into every subscriber queue so blocked generators exit.
# Without it they would keep clients connected to a discarded output, and those
# clients would never reconnect to the new one.
SHUTDOWN = object()

CONTENT_TYPES = {
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "png": "image/png",
    "bmp": "image/bmp",
}


def offer(subscriber: queue.Queue, item: Any) -> None:
    """Replace whatever a subscriber has queued with ``item``.

    Queues hold one element. A subscriber that hasn't drained it is behind and
    wants the newest frame, not the one it missed. Dropping instead of blocking
    keeps a stuck client from stalling the render thread.
    """
    try:
        subscriber.get_nowait()
    except queue.Empty:
        pass
    try:
        subscriber.put_nowait(item)
    except queue.Full:
        pass


@register_output("stream")
class StreamOutput(Output):
    needs_display = False

    def __init__(
        self,
        image_format: str = "jpeg",
        debounce_ms: int = 200,
        render_config: dict | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.image_format = image_format
        self.debounce = debounce_ms / 1000.0
        self.preferred_fps = (render_config or {}).get("fps-limit", 10)
        self.content_type = CONTENT_TYPES.get(image_format, "application/octet-stream")

        # Everything below is read from Flask threads and written from the
        # render thread.
        self._lock = threading.Lock()
        self._frame: bytes | None = None
        self._etag: str | None = None
        self._subscribers: set[queue.Queue] = set()

        # Render thread only.
        self._pending: pygame.Surface | None = None
        self._last_change = 0.0

    def wants_update(self) -> bool:
        """Always true, so the main loop keeps calling on_frame. The debounce
        timer needs those calls to tick once the tree stops changing."""
        return True

    def on_frame(self, surface: pygame.Surface, freshly_rendered: bool) -> None:
        """Publish once the tree has held still for the debounce interval.

        Nothing is encoded until then, so an idle dashboard uses no CPU. A
        transition that dirties the tree over many passes publishes one frame
        at the end instead of one per pass.
        """
        now = time.monotonic()
        if freshly_rendered:
            self._pending = surface
            self._last_change = now
            return
        if self._pending is None or now - self._last_change < self.debounce:
            return
        self._publish(self._pending)
        self._pending = None

    def current_frame(self) -> tuple[bytes | None, str | None]:
        with self._lock:
            return self._frame, self._etag

    def subscribe(self) -> queue.Queue:
        subscriber: queue.Queue = queue.Queue(maxsize=1)
        with self._lock:
            self._subscribers.add(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue) -> None:
        with self._lock:
            self._subscribers.discard(subscriber)

    def stop(self) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
            self._subscribers.clear()
        for subscriber in subscribers:
            offer(subscriber, SHUTDOWN)

    def _publish(self, surface: pygame.Surface) -> None:
        data = self._encode(surface)
        # Hash the encoded bytes to deduplicate. A re-render that produces
        # identical pixels keeps its ETag, so clients get a 304 and do not
        # repaint.
        etag = hashlib.blake2b(data, digest_size=8).hexdigest()
        with self._lock:
            if etag == self._etag:
                return
            self._frame, self._etag = data, etag
            subscribers = list(self._subscribers)
        self.logger.debug("Published frame %s (%d bytes)", etag, len(data))
        for subscriber in subscribers:
            offer(subscriber, etag)

    def _encode(self, surface: pygame.Surface) -> bytes:
        buf = io.BytesIO()
        if self.image_format in ("jpg", "jpeg"):
            # JPEG has no alpha channel, so flatten the tree's SRCALPHA
            # surface onto an opaque one first.
            opaque = pygame.Surface(surface.get_size())
            opaque.blit(surface, (0, 0))
            surface = opaque
        pygame.image.save(surface, buf, f"image.{self.image_format}")
        return buf.getvalue()
