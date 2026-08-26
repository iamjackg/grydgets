"""In-memory frame stream for remote displays.

Keeps the latest frame and the set of subscribers waiting to be told it
changed. Displays ask for it at their own resolution and each size is encoded
once, so a screen never scales what it receives and never downloads pixels it
is about to throw away.

The HTTP endpoints that serve them live in ``cli.py``, because Flask routes
cannot be unregistered and SIGUSR1 recreates every output -- an output that
registered its own routes would fail on the second reload.
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

# Encoded sizes kept per published frame. Every publish clears them, so this
# only has to cover the distinct display sizes asking within one frame's life.
MAX_VARIANTS = 8

CONTENT_TYPES = {
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "png": "image/png",
    "bmp": "image/bmp",
}


def _variant_etag(etag: str, size: tuple[int, int]) -> str:
    """Tag the frame identity with the size it was encoded at.

    Two displays holding the same frame at different sizes hold different
    bytes, so an ETag that named only the frame would 304 one of them into
    keeping the wrong size.
    """
    return f"{etag}-{size[0]}x{size[1]}"


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
        # render thread, except _variants, which request threads also fill in.
        self._lock = threading.Lock()
        self._frame: pygame.Surface | None = None
        self._etag: str | None = None
        # Wall-clock time.time(), not time.monotonic() -- clients compare it
        # against their own wall clock to measure end-to-end latency.
        self._published_at: float | None = None
        self._variants: dict[tuple[int, int], bytes] = {}
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

    def current_etag(
        self, size: tuple[int, int] | None = None
    ) -> tuple[str | None, float | None]:
        """The ETag a frame at ``size`` would carry, encoding nothing.

        Lets a caller that already holds this frame be answered with a 304
        without the server encoding a copy to compare it against. With no
        size the tag names the frame alone, which is what the event stream
        announces.
        """
        with self._lock:
            if self._frame is None:
                return None, None
            if size is None:
                return self._etag, self._published_at
            return _variant_etag(self._etag, tuple(size)), self._published_at

    def current_frame(
        self, size: tuple[int, int] | None = None
    ) -> tuple[bytes | None, str | None, float | None]:
        """The current frame encoded at ``size``, defaulting to as rendered.

        The first caller to ask for a size pays for the scale and the encode;
        the rest of the displays on that size get the cached bytes.
        """
        with self._lock:
            surface, source, published_at = self._frame, self._etag, self._published_at
            if surface is None:
                return None, None, None
            key = tuple(size) if size else surface.get_size()
            etag = source if size is None else _variant_etag(source, key)
            data = self._variants.get(key)

        if data is None:
            data = self._encode(surface, key)
            self.logger.debug(
                "Encoded frame %s at %dx%d (%d bytes)",
                source, key[0], key[1], len(data),
            )
            with self._lock:
                # A publish while this was encoding cleared the cache, and
                # these bytes are no longer what a display should be given.
                if source == self._etag:
                    if len(self._variants) >= MAX_VARIANTS:
                        self._variants.pop(next(iter(self._variants)))
                    self._variants[key] = data

        return data, etag, published_at

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
        # Hash the pixels rather than an encoding of them: nothing is encoded
        # until a display asks, and each one asks at its own size. A re-render
        # that produces identical pixels keeps its ETag, so displays get a 304
        # and do not repaint.
        etag = hashlib.blake2b(
            pygame.image.tobytes(surface, "RGB"), digest_size=8
        ).hexdigest()
        with self._lock:
            if etag == self._etag:
                return
            published_at = time.time()
            # Copy, because the render thread goes on drawing into the surface
            # it handed over and the encoding now happens later, elsewhere.
            self._frame = surface.copy()
            self._etag = etag
            self._published_at = published_at
            self._variants.clear()
            subscribers = list(self._subscribers)
        self.logger.debug("Published frame %s", etag)
        for subscriber in subscribers:
            offer(subscriber, (etag, published_at))

    def _encode(self, surface: pygame.Surface, size: tuple[int, int]) -> bytes:
        buf = io.BytesIO()
        if surface.get_size() != size:
            surface = pygame.transform.smoothscale(surface, size)
        if self.image_format in ("jpg", "jpeg"):
            # JPEG has no alpha channel, so flatten the tree's SRCALPHA
            # surface onto an opaque one first.
            opaque = pygame.Surface(surface.get_size())
            opaque.blit(surface, (0, 0))
            surface = opaque
        pygame.image.save(surface, buf, f"image.{self.image_format}")
        return buf.getvalue()
