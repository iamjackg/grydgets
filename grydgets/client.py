"""Frame viewer for a dashboard rendered on another machine.

Holds an SSE connection to a grydgets instance running a ``stream`` output and
fetches each new frame at this screen's resolution, scaling one only if it
arrives at some other size. The client does not create widgets or providers
and does almost no rendering at all, which keeps it light.

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

logger = logging.getLogger("grydgets.client")

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

    The queue only holds the most recent frame -- a display that hasn't picked
    up the previous one only needs the latest, not a backlog.
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

    def __init__(
        self,
        server: dict,
        resolution: tuple[int, int],
        stop_event: threading.Event,
    ) -> None:
        super().__init__(daemon=True)
        self.logger = logging.getLogger("FrameSource")
        base = server["url"]
        if not base.endswith("/"):
            base += "/"
        self.frame_url = urljoin(base, "frame")
        self.events_url = urljoin(base, "events")
        self.reconnect_delay = server["reconnect_delay"]
        self.stale_after = server["stale_after"]
        # Asking for this screen's size gets frames already scaled to it. A
        # server too old to understand it sends them as rendered, and decode()
        # scales them here instead.
        self.params = {"width": resolution[0], "height": resolution[1]}
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

    def fetch_frame(self, notified_at: float | None = None) -> None:
        """Fetch the current frame unless the server says we already have it.

        ``notified_at`` is when the caller learned a new frame exists -- the
        time the SSE ``data:`` line was read. It is ``None`` for the
        unconditional startup fetch, which is not a response to an event.
        """
        headers = dict(self.headers)
        if self._etag:
            headers["If-None-Match"] = self._etag
        fetch_start = time.time()
        response = self.session.get(
            self.frame_url, params=self.params, headers=headers, timeout=FETCH_TIMEOUT
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
        fetch_end = time.time()
        self._etag = response.headers.get("ETag")
        hint = EXTENSIONS.get(response.headers.get("Content-Type", ""), "frame")
        published_at = None
        header = response.headers.get("X-Frame-Published-At")
        if header is not None:
            try:
                published_at = float(header)
            except ValueError:
                pass
        metrics = {
            "published_at": published_at,
            "notified_at": notified_at,
            "fetch_start": fetch_start,
            "fetch_end": fetch_end,
        }
        offer(self.frames, (response.content, hint, metrics))

    def stream_events(self) -> None:
        """Fetch a frame for every event, until the connection drops."""
        response = self.session.get(
            self.events_url,
            params=self.params,
            headers=self.headers,
            stream=True,
            timeout=EVENTS_TIMEOUT,
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
                    self.fetch_frame(notified_at=time.time())


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


def fit_font(text: str, line_height: int, max_width: int) -> pygame.font.Font:
    """The bundled default font, about ``line_height`` tall and no wider than
    ``max_width`` for ``text``.

    pygame's default font is used rather than a shipped one so the viewer still
    needs no font assets. A ``pygame.font.Font`` size is not its line height,
    so ask for one and correct; then shrink, because a size that fits a clock
    across the screen can overflow with a longer message.
    """
    size = max(8, round(line_height))
    font = pygame.font.Font(None, size)
    height = font.get_height()
    if height and height != line_height:
        size = max(8, round(size * line_height / height))
        font = pygame.font.Font(None, size)
    while size > 8 and font.size(text)[0] > max_width:
        size = round(size * 0.9)
        font = pygame.font.Font(None, size)
    return font


class OfflineScreen:
    """The last frame dimmed, under a large clock and a message.

    Optional, and separate from the staleness indicator: a screen showing this
    has given up on the server for now and is being useful as a clock instead.
    It works with no frame at all, so a viewer that boots while the server is
    down still shows the time.
    """

    def __init__(self, resolution: tuple[int, int], settings: dict) -> None:
        self.resolution = resolution
        self.message = settings["message"]
        self.clock_format = settings["clock_format"]
        width, height = resolution
        self.shade = pygame.Surface(resolution)
        self.shade.fill((0, 0, 0))
        self.shade.set_alpha(round(255 * settings["dim"]))
        self.max_width = round(width * 0.9)
        self.clock_height = max(12, round(height * 0.40))
        self.message_font = fit_font(
            self.message, max(10, round(height * 0.09)), self.max_width
        )
        self.gap = round(height * 0.03)
        # Dimming a 1080p frame is not free, and the frame does not change
        # while the server is unreachable -- only the clock does.
        self._source: pygame.Surface | None = None
        self._background: pygame.Surface | None = None

    def clock_text(self) -> str:
        return time.strftime(self.clock_format)

    def background(self, frame: pygame.Surface | None) -> pygame.Surface:
        """The dimmed frame, or black before any frame has arrived."""
        if self._background is None or frame is not self._source:
            background = pygame.Surface(self.resolution)
            background.fill((0, 0, 0))
            if frame is not None:
                background.blit(frame, (0, 0))
                background.blit(self.shade, (0, 0))
            self._source = frame
            self._background = background
        return self._background

    def render(self, frame: pygame.Surface | None, clock_text: str) -> pygame.Surface:
        """Clock over message, centred as a block on the dimmed frame.

        Positioned by each surface's inked area rather than its full height.
        The font leaves room above digits for accents nothing here uses, which
        would push the block visibly low.
        """
        surface = self.background(frame).copy()
        clock_font = fit_font(clock_text, self.clock_height, self.max_width)
        clock = clock_font.render(clock_text, True, (255, 255, 255))
        message = self.message_font.render(self.message, True, (255, 255, 255))
        clock_ink = clock.get_bounding_rect()
        message_ink = message.get_bounding_rect()

        centre = self.resolution[0] / 2
        block = clock_ink.height + self.gap + message_ink.height
        top = (self.resolution[1] - block) / 2
        surface.blit(
            clock,
            (round(centre - clock_ink.centerx), round(top - clock_ink.top)),
        )
        surface.blit(
            message,
            (
                round(centre - message_ink.centerx),
                round(top + clock_ink.height + self.gap - message_ink.top),
            ),
        )
        return surface


def latency_lines(metrics: dict, displayed_at: float) -> list[str]:
    """Format how long a frame took to notice, download, and display.

    ``published_at`` is the server's ``time.time()``, everything else is this
    client's own wall clock -- the numbers drift with any clock skew between
    the two machines. ``notified_at`` is ``None`` for the unconditional
    startup fetch, since that one is not a response to an SSE event.
    """
    published_at = metrics["published_at"]
    if published_at is None:
        return ["latency: no timestamp from server"]
    notified_at = metrics["notified_at"]
    fetch_start = metrics["fetch_start"]
    fetch_end = metrics["fetch_end"]
    lines = []
    if notified_at is not None:
        lines.append(f"notice   {(notified_at - published_at) * 1000:5.0f} ms")
    lines.append(f"download {(fetch_end - fetch_start) * 1000:5.0f} ms")
    lines.append(f"display  {(displayed_at - fetch_end) * 1000:5.0f} ms")
    lines.append(f"total    {(displayed_at - published_at) * 1000:5.0f} ms")
    return lines


def build_metrics_overlay(font: pygame.font.Font, lines: list[str]) -> pygame.Surface:
    """A translucent panel of latency lines, for ``logging.level: debug``.

    Uses pygame's bundled default font rather than a shipped font file --
    the whole point of the client is to need none.
    """
    rendered = [font.render(line, True, (255, 255, 255)) for line in lines]
    pad = round(font.get_height() * 0.4)
    width = max(s.get_width() for s in rendered) + pad * 2
    height = sum(s.get_height() for s in rendered) + pad * 2
    surface = pygame.Surface((width, height), pygame.SRCALPHA)
    pygame.draw.rect(
        surface, (0, 0, 0, 170), surface.get_rect(), border_radius=round(pad * 0.5)
    )
    y = pad
    for line_surface in rendered:
        surface.blit(line_surface, (pad, y))
        y += line_surface.get_height()
    return surface


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
    source = FrameSource(conf["server"], resolution, stop_event)

    output.pre_init()
    pygame.init()
    pygame.mixer.quit()
    output.setup(resolution)

    indicator = build_indicator(resolution)
    corner = indicator_position(resolution, indicator, conf["indicator"]["corner"])

    offline = None
    if conf["offline"]["enabled"]:
        offline = OfflineScreen(resolution, conf["offline"])

    # logging.level: debug also turns on the latency overlay -- there is
    # nothing else that level would be for on a viewer with no widget tree.
    debug = conf["logging"]["level"] == "debug"
    metrics_font = None
    if debug:
        metrics_font = pygame.font.Font(None, max(10, round(16 * min(resolution) / 1080)))

    source.start()

    clock = pygame.time.Clock()
    # The last good frame, never drawn on. The indicator and the latency
    # overlay go onto a copy; drawing on this one would stack another copy
    # onto it at every repaint.
    frame = None
    showing_stale = None
    showing_clock = None
    metrics_surface = None
    metrics_corner = None
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
                data, hint, metrics = payload
                decoded = decode((data, hint), resolution)
                if decoded is not None:
                    frame = decoded
                    repaint = True
                    if debug:
                        displayed_at = time.time()
                        lines = latency_lines(metrics, displayed_at)
                        logger.debug("frame latency: %s", "  ".join(lines))
                        metrics_surface = build_metrics_overlay(metrics_font, lines)
                        metrics_corner = indicator_position(
                            resolution, metrics_surface, "top-left"
                        )

            stale = source.is_stale()
            if stale != showing_stale:
                repaint = True

            clock_text = None
            if offline is not None and stale:
                # The clock is the only thing moving on the offline screen, so
                # repaint on the string changing rather than every tick. That
                # follows whatever resolution clock_format asks for.
                clock_text = offline.clock_text()
                if clock_text != showing_clock:
                    repaint = True

            if repaint and (frame is not None or clock_text is not None):
                if clock_text is not None:
                    shown = offline.render(frame, clock_text)
                    if metrics_surface is not None:
                        shown.blit(metrics_surface, metrics_corner)
                else:
                    shown = frame
                    if stale or metrics_surface is not None:
                        shown = frame.copy()
                        if stale:
                            shown.blit(indicator, corner)
                        if metrics_surface is not None:
                            shown.blit(metrics_surface, metrics_corner)
                output.on_frame(shown, True)
                showing_stale = stale
                showing_clock = clock_text

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
    # urllib3 logs a line per request and per reconnect. At debug level that
    # buries the frame timings, which are the reason to be at debug level.
    logging.getLogger("urllib3").setLevel(logging.INFO)
    run(conf)


if __name__ == "__main__":
    main()
