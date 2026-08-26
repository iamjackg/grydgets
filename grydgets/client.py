"""Frame viewer for a dashboard rendered on another machine.

Holds an SSE connection to a grydgets instance running a ``stream`` output,
fetches each new frame, scales it to this screen and displays it. No widget
tree, no providers, no compositing.

Nothing here imports ``grydgets.widgets``, ``grydgets.providers`` or flask, and
it must stay that way -- a small footprint is the reason to run a viewer at
all. ``create_outputs`` imports every output module to register them, so keep
widget imports out of those too.
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import queue
import sys
import threading
import time
from typing import Any
from urllib.parse import urljoin

import pygame
import requests

from grydgets import config
from grydgets.outputs import Output, create_outputs

logging.basicConfig(
    format="[%(asctime)s] %(levelname)s:%(name)s:%(message)s", level=logging.INFO
)

# The viewer idles between frames. This only sets how quickly it notices a
# window close and how soon the staleness indicator appears.
CLIENT_FPS = 20

# Connect and read timeouts for a one-shot frame fetch.
FETCH_TIMEOUT = (5, 30)

# The server sends a comment line every 20 seconds. A read that waits this long
# without one is a connection that died without saying so.
EVENTS_TIMEOUT = (5, 45)

# A bad token is a configuration error that will not fix itself, so back off
# much harder than for a dropped connection. A client hammering a server that
# keeps rejecting it is hard to diagnose from the server end.
AUTH_BACKOFF = 300

EXTENSIONS = {
    "image/jpeg": "frame.jpg",
    "image/png": "frame.png",
    "image/bmp": "frame.bmp",
}


class AuthRejected(Exception):
    """The server answered 401."""


def offer(destination: queue.Queue, item: Any) -> None:
    """Replace whatever is queued with ``item``.

    The queue holds one frame. A frame the display hasn't picked up is already
    out of date, so drop it rather than build a backlog.
    """
    try:
        destination.get_nowait()
    except queue.Empty:
        pass
    try:
        destination.put_nowait(item)
    except queue.Full:
        pass


class FrameSource(threading.Thread):
    """Keeps the connection to the server, off the display thread.

    This produces encoded bytes and nothing else; all pygame work stays on the
    main thread. It also keeps the window responsive while the event stream
    sits idle.
    """

    def __init__(self, server: dict, stop_event: threading.Event) -> None:
        super().__init__(daemon=True)
        self.logger = logging.getLogger("FrameSource")
        base = server["url"]
        if not base.endswith("/"):
            base += "/"
        self.frame_url = urljoin(base, "frame")
        self.events_url = urljoin(base, "events")
        self.reconnect_delay = server["reconnect_delay"]
        self.stale_after = server["stale_after"]
        self.headers = {}
        if server.get("token"):
            self.headers["Authorization"] = f"Bearer {server['token']}"
        self.stop_event = stop_event
        self.session = requests.Session()
        self.frames: queue.Queue = queue.Queue(maxsize=1)

        self._etag: str | None = None
        # Set while nothing is connected; None while the event stream is open.
        # Read from the display thread, written here.
        self._disconnected_since: float | None = time.monotonic()
        self._auth_failed = False

    def is_stale(self) -> bool:
        """Whether the display should be showing the staleness indicator."""
        if self._auth_failed:
            return True
        since = self._disconnected_since
        return since is not None and time.monotonic() - since >= self.stale_after

    def run(self) -> None:
        while not self.stop_event.is_set():
            delay = self.reconnect_delay
            try:
                # Fetch before connecting. Otherwise a viewer that just booted
                # shows nothing until the next change, possibly minutes away.
                self.fetch_frame()
                self.stream_events()
                self.logger.info("The server closed the event stream")
            except AuthRejected as e:
                delay = AUTH_BACKOFF
                self._auth_failed = True
                self.logger.error(
                    "%s -- check server.token against the server's "
                    "server.auth.stream_token. Retrying in %d seconds",
                    e, delay,
                )
            except requests.RequestException as e:
                # Log only the first failure of a run. A viewer left running
                # against a server that is down for hours would otherwise
                # repeat the same line every reconnect_delay seconds and bury
                # anything else that went wrong.
                if self._disconnected_since is None:
                    self.logger.warning("%s", e)
                else:
                    self.logger.debug("%s", e)
            except Exception:
                self.logger.exception("Unexpected failure talking to the server")

            if self._disconnected_since is None:
                self._disconnected_since = time.monotonic()
            self.stop_event.wait(delay)

    def fetch_frame(self) -> None:
        """Fetch the current frame unless the server says we already have it."""
        headers = dict(self.headers)
        if self._etag:
            headers["If-None-Match"] = self._etag
        response = self.session.get(
            self.frame_url, headers=headers, timeout=FETCH_TIMEOUT
        )
        if response.status_code == 401:
            raise AuthRejected(f"{self.frame_url} rejected the token")
        self._auth_failed = False
        if response.status_code == 304:
            return
        if response.status_code == 503:
            self.logger.info("The server has not published a frame yet")
            return
        response.raise_for_status()
        self._etag = response.headers.get("ETag")
        hint = EXTENSIONS.get(response.headers.get("Content-Type", ""), "frame")
        offer(self.frames, (response.content, hint))

    def stream_events(self) -> None:
        """Fetch a frame for every event, until the connection drops."""
        response = self.session.get(
            self.events_url, headers=self.headers, stream=True, timeout=EVENTS_TIMEOUT
        )
        if response.status_code == 401:
            raise AuthRejected(f"{self.events_url} rejected the token")
        response.raise_for_status()
        with response:
            self._disconnected_since = None
            self.logger.info("Connected to %s", self.events_url)
            for line in response.iter_lines(decode_unicode=True):
                if self.stop_event.is_set():
                    return
                # Blank separators and ": ping" comments carry nothing. The
                # ping exists to make a dead connection fail a read.
                if line and line.startswith("data:"):
                    self.fetch_frame()


def build_indicator(resolution: tuple[int, int]) -> pygame.Surface:
    """An amber warning triangle on a dark translucent pad.

    Drawn rather than loaded, so the viewer needs no font and no image asset.
    The pad keeps it visible against a light day theme as well as a dark night
    one. The size follows the screen so it looks the same on all of them.
    """
    size = max(16, round(48 * min(resolution) / 1080))
    pad = round(size * 1.4)
    surface = pygame.Surface((pad, pad), pygame.SRCALPHA)
    pygame.draw.rect(
        surface, (0, 0, 0, 170), surface.get_rect(), border_radius=round(pad * 0.2)
    )

    inset = (pad - size) / 2
    amber = (255, 176, 32)
    dark = (32, 24, 0)
    pygame.draw.polygon(
        surface,
        amber,
        [
            (pad / 2, inset),
            (inset, pad - inset),
            (pad - inset, pad - inset),
        ],
    )

    bar_width = max(2, round(size * 0.11))
    bar_top = inset + size * 0.34
    bar_bottom = inset + size * 0.66
    pygame.draw.rect(
        surface,
        dark,
        pygame.Rect(
            round(pad / 2 - bar_width / 2),
            round(bar_top),
            bar_width,
            round(bar_bottom - bar_top),
        ),
    )
    # A square, not a circle. The dot is a few pixels across on a 768-line
    # screen, and pygame draws a circle that small as a diamond.
    pygame.draw.rect(
        surface,
        dark,
        pygame.Rect(
            round(pad / 2 - bar_width / 2),
            round(inset + size * 0.75),
            bar_width,
            bar_width,
        ),
    )
    return surface


def indicator_position(
    resolution: tuple[int, int], indicator: pygame.Surface, corner: str
) -> tuple[int, int]:
    margin = round(min(resolution) * 0.025)
    width, height = indicator.get_size()
    x = margin if corner.endswith("left") else resolution[0] - width - margin
    y = margin if corner.startswith("top") else resolution[1] - height - margin
    return x, y


def decode(payload: tuple[bytes, str], resolution: tuple[int, int]):
    """Turn received bytes into a surface the size of this screen."""
    data, hint = payload
    try:
        image = pygame.image.load(io.BytesIO(data), hint)
    except pygame.error as e:
        logging.warning("Could not decode the frame from the server: %s", e)
        return None
    image = image.convert()
    if image.get_size() != resolution:
        # Always smoothscale. Nearest-neighbour breaks digit strokes at these
        # ratios -- "00" comes out as "]0". Unrelated to the server's
        # graphics.smooth-scaling, which applies to ImageWidget.
        image = pygame.transform.smoothscale(image, resolution)
    return image


def run(conf: dict) -> None:
    resolution = tuple(conf["graphics"]["resolution"])
    outputs = create_outputs(conf["outputs"], {})
    output: Output = outputs[0]

    stop_event = threading.Event()
    source = FrameSource(conf["server"], stop_event)

    output.pre_init()
    pygame.init()
    pygame.mixer.quit()
    output.setup(resolution)

    indicator = build_indicator(resolution)
    corner = indicator_position(resolution, indicator, conf["indicator"]["corner"])

    source.start()

    clock = pygame.time.Clock()
    # The last good frame, never drawn on. The indicator goes onto a copy;
    # drawing on this one would stack a triangle on it at every repaint.
    frame = None
    showing_stale = None
    try:
        while not stop_event.is_set():
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    stop_event.set()
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    stop_event.set()

            repaint = False
            try:
                payload = source.frames.get_nowait()
            except queue.Empty:
                payload = None
            if payload is not None:
                decoded = decode(payload, resolution)
                if decoded is not None:
                    frame = decoded
                    repaint = True

            stale = source.is_stale()
            if stale != showing_stale:
                repaint = True

            if repaint and frame is not None:
                if stale:
                    shown = frame.copy()
                    shown.blit(indicator, corner)
                else:
                    shown = frame
                output.on_frame(shown, True)
                showing_stale = stale

            clock.tick(CLIENT_FPS)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        output.stop()
        pygame.quit()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Grydgets remote display: show frames rendered elsewhere"
    )
    parser.add_argument(
        "--config",
        default="client.yaml",
        metavar="FILE",
        help="Client configuration file (default: client.yaml)",
    )
    parser.add_argument(
        "--config-dir",
        default=None,
        metavar="DIR",
        help="Directory containing the config file (default: current directory)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    config_dir = None
    if args.config_dir is not None:
        try:
            os.chdir(args.config_dir)
        except OSError as e:
            sys.exit(f"grydgets-client: --config-dir {args.config_dir}: {e.strerror}")
        config_dir = os.getcwd()

    try:
        conf = config.load_client_config(args.config)
    except config.ConfigError as e:
        message = f"grydgets-client: {e}"
        if config_dir is not None:
            message += f"\ngrydgets-client: config paths are relative to {config_dir}"
        sys.exit(message)

    logging.getLogger().setLevel(logging.getLevelName(conf["logging"]["level"].upper()))
    run(conf)


if __name__ == "__main__":
    main()
