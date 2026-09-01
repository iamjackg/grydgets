"""Tests for the remote display: config shape, StreamOutput, and the helpers
the frame endpoints are built from.

Run with: uv run --with pytest python -m pytest tests/test_remote_display.py
"""

import io
import os
import queue
import threading

import pytest
import voluptuous

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from grydgets import config
from grydgets.config import ConfigError
from grydgets.outputs import create_outputs
from grydgets.outputs import stream
from grydgets.outputs.stream import SHUTDOWN, StreamOutput, offer


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text)
    return str(path)


def test_conf_yaml_loads_without_a_server_block(tmp_path):
    """conf-pi.yaml has no server: block and must still load."""
    path = write(tmp_path, "conf.yaml", """
graphics:
  resolution: [480, 320]
logging:
  level: info
""")
    conf = config.load_config(path)
    assert "server" not in conf


def test_server_settings_fills_in_what_the_file_left_out():
    assert config.server_settings({}) == {
        "host": "127.0.0.1",
        "port": 5000,
        "auth": {},
    }
    conf = {"server": {"host": "0.0.0.0", "auth": {"stream_token": "t"}}}
    assert config.server_settings(conf) == {
        "host": "0.0.0.0",
        "port": 5000,
        "auth": {"stream_token": "t"},
    }


def test_the_two_tokens_are_independently_optional(tmp_path):
    path = write(tmp_path, "conf.yaml", """
graphics:
  resolution: [480, 320]
logging:
  level: info
server:
  auth:
    stream_token: only-this-one
""")
    conf = config.load_config(path)
    auth = config.server_settings(conf)["auth"]
    assert auth["stream_token"] == "only-this-one"
    assert "control_token" not in auth


def test_http_control_is_off_unless_asked_for():
    """An appearance block describes a look. Only this key opens a port."""
    validated = voluptuous.Schema(config.appearance_schema)(
        {"themes": {"day": "d", "night": "n"}}
    )
    assert validated["http_control"] is False


def test_a_stream_output_validates_and_is_registered(tmp_path):
    path = write(tmp_path, "conf.yaml", """
graphics:
  resolution: [480, 320]
logging:
  level: info
outputs:
  - type: stream
""")
    conf = config.load_config(path)
    outputs = create_outputs(conf["outputs"], conf["graphics"])
    assert isinstance(outputs[0], StreamOutput)
    assert outputs[0].content_type == "image/jpeg"


def test_an_unknown_output_type_lists_what_is_available(tmp_path):
    path = write(tmp_path, "conf.yaml", """
graphics:
  resolution: [480, 320]
logging:
  level: info
outputs:
  - type: streem
""")
    with pytest.raises(ConfigError) as e:
        config.load_config(path)
    assert "stream" in str(e.value)


@pytest.fixture
def surfaces():
    pygame.init()
    pygame.display.set_mode((1, 1))
    red = pygame.Surface((20, 20))
    red.fill((255, 0, 0))
    blue = pygame.Surface((20, 20))
    blue.fill((0, 0, 255))
    yield red, blue
    pygame.quit()


def test_nothing_is_published_until_the_tree_stops_changing(surfaces):
    """A transition dirtying the tree over many passes costs one encode."""
    red, blue = surfaces
    output = StreamOutput(debounce_ms=1000)

    for _ in range(5):
        output.on_frame(red, freshly_rendered=True)
    assert output.current_frame() == (None, None, None)

    # Still inside the debounce window.
    output.on_frame(red, freshly_rendered=False)
    assert output.current_frame() == (None, None, None)

    output.debounce = 0
    output.on_frame(red, freshly_rendered=False)
    data, etag, published_at = output.current_frame()
    assert data is not None and etag is not None and published_at is not None


def publish(output, surface):
    output.on_frame(surface, freshly_rendered=True)
    output.on_frame(surface, freshly_rendered=False)


def test_a_frame_is_encoded_at_the_size_the_display_asked_for(surfaces):
    """The display should never have to scale what it receives."""
    red, _ = surfaces
    output = StreamOutput(debounce_ms=0, image_format="bmp")
    publish(output, red)

    data, _, _ = output.current_frame((40, 10))
    assert pygame.image.load(io.BytesIO(data), "frame.bmp").get_size() == (40, 10)

    # Asking for no size in particular gets the frame as it was rendered.
    data, _, _ = output.current_frame()
    assert pygame.image.load(io.BytesIO(data), "frame.bmp").get_size() == red.get_size()


def test_sizes_are_encoded_once_and_then_served_from_the_cache(surfaces):
    red, blue = surfaces
    output = StreamOutput(debounce_ms=0)
    publish(output, red)

    encodes = []
    real_encode = output._encode
    output._encode = lambda surface, size: encodes.append(size) or real_encode(
        surface, size
    )

    output.current_frame((40, 10))
    output.current_frame((40, 10))
    output.current_frame((20, 5))
    assert encodes == [(40, 10), (20, 5)]

    # A new frame invalidates every size, not just the one asked for next.
    publish(output, blue)
    output.current_frame((40, 10))
    assert encodes == [(40, 10), (20, 5), (40, 10)]


def test_only_so_many_sizes_are_cached(surfaces):
    """A caller naming size after size must not grow the cache forever."""
    red, _ = surfaces
    output = StreamOutput(debounce_ms=0)
    publish(output, red)

    for width in range(1, stream.MAX_VARIANTS + 5):
        output.current_frame((width, 10))
    assert len(output._variants) == stream.MAX_VARIANTS


def test_the_etag_covers_the_size_as_well_as_the_pixels(surfaces):
    """Two screens holding one frame at two sizes hold different bytes."""
    red, blue = surfaces
    output = StreamOutput(debounce_ms=0)
    publish(output, red)

    _, small, _ = output.current_frame((40, 10))
    _, large, _ = output.current_frame((80, 20))
    assert small != large

    publish(output, blue)
    _, changed, _ = output.current_frame((40, 10))
    assert changed != small


def test_the_etag_is_available_without_encoding_anything(surfaces):
    """So a display that already has the frame is 304ed for free."""
    red, _ = surfaces
    output = StreamOutput(debounce_ms=0)
    assert output.current_etag((40, 10)) == (None, None)

    publish(output, red)
    etag, published_at = output.current_etag((40, 10))
    assert output._variants == {}

    data, encoded_etag, encoded_at = output.current_frame((40, 10))
    assert (encoded_etag, encoded_at) == (etag, published_at)


def test_a_frame_encoded_after_a_newer_one_arrives_is_not_cached(surfaces):
    """Its bytes are already stale; caching them would serve them again."""
    red, blue = surfaces
    output = StreamOutput(debounce_ms=0)
    publish(output, red)

    real_encode = output._encode

    def encode_then_publish(surface, size):
        data = real_encode(surface, size)
        output._encode = real_encode
        publish(output, blue)
        return data

    output._encode = encode_then_publish
    output.current_frame((40, 10))
    assert output._variants == {}


def test_identical_pixels_keep_their_etag(surfaces):
    """A re-render that changes nothing must not make clients repaint."""
    red, blue = surfaces
    output = StreamOutput(debounce_ms=0)

    output.on_frame(red, freshly_rendered=True)
    output.on_frame(red, freshly_rendered=False)
    _, first, _ = output.current_frame()

    output.on_frame(red, freshly_rendered=True)
    output.on_frame(red, freshly_rendered=False)
    _, again, _ = output.current_frame()
    assert again == first

    output.on_frame(blue, freshly_rendered=True)
    output.on_frame(blue, freshly_rendered=False)
    _, changed, _ = output.current_frame()
    assert changed != first


def test_subscribers_are_told_the_new_etag_and_when_it_was_published(surfaces):
    red, blue = surfaces
    output = StreamOutput(debounce_ms=0)
    subscriber = output.subscribe()

    output.on_frame(red, freshly_rendered=True)
    output.on_frame(red, freshly_rendered=False)
    _, etag, published_at = output.current_frame()
    assert subscriber.get_nowait() == (etag, published_at)

    output.unsubscribe(subscriber)
    output.on_frame(blue, freshly_rendered=True)
    output.on_frame(blue, freshly_rendered=False)
    with pytest.raises(queue.Empty):
        subscriber.get_nowait()


def test_a_subscriber_that_is_behind_drops_frames_rather_than_queueing_them():
    """A stuck client must not grow a backlog or stall the render thread."""
    subscriber = queue.Queue(maxsize=1)
    offer(subscriber, "first")
    offer(subscriber, "second")
    offer(subscriber, "third")
    assert subscriber.get_nowait() == "third"
    assert subscriber.empty()


def test_encoding_happens_off_the_calling_thread(surfaces):
    """Request threads must not allocate frame-sized buffers of their own: a
    glibc arena per HTTP thread is memory the process never gives back."""
    red, _ = surfaces
    output = StreamOutput(debounce_ms=0)
    publish(output, red)

    threads = []
    real_encode = output._encode
    output._encode = lambda surface, size: threads.append(
        threading.current_thread()
    ) or real_encode(surface, size)

    output.current_frame((40, 10))
    assert threads == [output._encoder]


def test_one_size_asked_for_at_once_costs_one_encode(surfaces):
    """Several displays on the same size share the encode rather than each
    paying for an identical copy of it."""
    red, _ = surfaces
    output = StreamOutput(debounce_ms=0)
    publish(output, red)

    started = threading.Event()
    release = threading.Event()
    encodes = []
    real_encode = output._encode

    def blocking_encode(surface, size):
        encodes.append(size)
        started.set()
        release.wait(5)
        return real_encode(surface, size)

    output._encode = blocking_encode

    results = []

    def ask():
        results.append(output.current_frame((40, 10)))

    first = threading.Thread(target=ask)
    first.start()
    # Hold the encode open so the others arrive while it is still running,
    # which is the case that would otherwise encode the same size four times.
    assert started.wait(5)

    rest = [threading.Thread(target=ask) for _ in range(3)]
    for caller in rest:
        caller.start()
    release.set()
    for caller in [first, *rest]:
        caller.join(5)

    assert encodes == [(40, 10)]
    assert len(results) == 4
    assert all(r == results[0] for r in results)


def test_a_caller_is_answered_even_if_the_output_is_stopped(surfaces):
    """A reload stops the old output while requests are still in flight
    against it. They need bytes back, not a wait that never ends."""
    red, _ = surfaces
    output = StreamOutput(debounce_ms=0)
    publish(output, red)
    output.stop()

    data, etag, published_at = output.current_frame((40, 10))
    assert data is not None and etag is not None and published_at is not None


def test_stopping_ends_the_encoder_thread(surfaces):
    """Otherwise every SIGUSR1 reload would leave one behind."""
    output = StreamOutput(debounce_ms=0)
    assert output._encoder.is_alive()
    output.stop()
    assert not output._encoder.is_alive()


def test_stopping_wakes_every_subscriber(surfaces):
    """A reload replaces the output, so its generators must exit and let their
    clients reconnect to the new one."""
    output = StreamOutput(debounce_ms=0)
    subscribers = [output.subscribe() for _ in range(3)]
    output.stop()
    assert all(s.get_nowait() is SHUTDOWN for s in subscribers)


def test_is_loopback():
    from grydgets.cli import is_loopback

    assert is_loopback("127.0.0.1")
    assert is_loopback("127.1.2.3")
    assert is_loopback("localhost")
    assert is_loopback("::1")
    assert not is_loopback("0.0.0.0")
    assert not is_loopback("192.168.1.10")
    assert not is_loopback("dashboard-host")


def test_etag_matches():
    from grydgets.cli import etag_matches

    assert etag_matches('"abc"', "abc")
    assert etag_matches('"xyz", "abc"', "abc")
    assert not etag_matches('"xyz"', "abc")
    # unquoted isn't an ETag
    assert not etag_matches("abc", "abc")
    assert not etag_matches(None, "abc")
    assert not etag_matches('"abc"', None)


def test_requested_size():
    from grydgets.cli import BadSize, requested_size

    assert requested_size({}) is None
    assert requested_size({"width": "1366", "height": "768"}) == (1366, 768)
    for args in (
        {"width": "1366"},                    # half a size is not a size
        {"height": "768"},
        {"width": "1366", "height": "hd"},
        {"width": "0", "height": "768"},
        {"width": "99999", "height": "768"},
    ):
        with pytest.raises(BadSize):
            requested_size(args)


CLIENT = """
server:
  url: http://dashboard-host:5000
graphics:
  resolution: [1366, 768]
outputs:
  - type: window
    fullscreen: true
"""


def test_client_config_applies_its_defaults(tmp_path):
    """Unlike load_config, this returns the validated document. The client
    reads reconnect_delay and stale_after straight out of it."""
    conf = config.load_client_config(write(tmp_path, "client.yaml", CLIENT))
    assert conf["server"]["reconnect_delay"] == 2
    assert conf["server"]["stale_after"] == 30
    assert conf["indicator"]["corner"] == "bottom-right"
    assert conf["logging"]["level"] == "info"


def test_a_client_cannot_configure_an_output_that_shows_nothing(tmp_path):
    conf = CLIENT.replace(
        "  - type: window\n    fullscreen: true",
        "  - type: file\n    output_path: ./out",
    )
    with pytest.raises(ConfigError) as e:
        config.load_client_config(write(tmp_path, "client.yaml", conf))
    assert "file" in str(e.value)


def test_a_client_shows_one_screen(tmp_path):
    conf = CLIENT + "  - type: framebuffer\n    device: /dev/fb1\n"
    with pytest.raises(ConfigError):
        config.load_client_config(write(tmp_path, "client.yaml", conf))


def test_a_client_needs_somewhere_to_fetch_from(tmp_path):
    conf = CLIENT.replace(
        "  url: http://dashboard-host:5000", "  stale_after: 30"
    )
    with pytest.raises(ConfigError) as e:
        config.load_client_config(write(tmp_path, "client.yaml", conf))
    assert "url" in str(e.value)


def test_the_indicator_scales_with_the_screen(surfaces):
    from grydgets.client import build_indicator, indicator_position

    big = build_indicator((1920, 1080))
    small = build_indicator((1366, 768))
    assert big.get_width() > small.get_width()

    # Every corner must place the whole indicator on screen.
    for corner in ("top-left", "top-right", "bottom-left", "bottom-right"):
        x, y = indicator_position((1366, 768), small, corner)
        assert 0 <= x and x + small.get_width() <= 1366
        assert 0 <= y and y + small.get_height() <= 768


def test_latency_lines_needs_a_published_at():
    from grydgets.client import latency_lines

    metrics = {"published_at": None, "notified_at": None, "fetch_start": 0, "fetch_end": 0}
    assert latency_lines(metrics, displayed_at=1.0) == ["latency: no timestamp from server"]


def test_latency_lines_skips_notice_without_an_sse_event():
    """The unconditional startup fetch never followed an SSE event."""
    from grydgets.client import latency_lines

    metrics = {
        "published_at": 100.0,
        "notified_at": None,
        "fetch_start": 100.1,
        "fetch_end": 100.15,
    }
    lines = latency_lines(metrics, displayed_at=100.2)
    assert not any(line.startswith("notice") for line in lines)
    assert any(line.startswith("download") for line in lines)
    assert any(line.startswith("total") for line in lines)


def test_latency_lines_covers_notice_download_display_and_total():
    from grydgets.client import latency_lines

    metrics = {
        "published_at": 100.0,
        "notified_at": 100.05,
        "fetch_start": 100.05,
        "fetch_end": 100.1,
    }
    lines = latency_lines(metrics, displayed_at=100.15)
    stages = [line.split()[0] for line in lines]
    assert stages == ["notice", "download", "display", "total"]


def test_the_metrics_overlay_renders_every_line(surfaces):
    from grydgets.client import build_metrics_overlay

    pygame.font.init()
    font = pygame.font.Font(None, 16)
    overlay = build_metrics_overlay(font, ["notice   10 ms", "total    50 ms"])
    assert overlay.get_width() > 0
    assert overlay.get_height() > 0


def test_the_offline_screen_is_off_unless_asked_for(tmp_path):
    conf = config.load_client_config(write(tmp_path, "client.yaml", CLIENT))
    assert conf["offline"]["enabled"] is False
    assert conf["offline"]["message"] == "Dashboard server unavailable"
    assert conf["offline"]["clock_format"] == "%H:%M"
    assert conf["offline"]["dim"] == 0.75


def test_the_dim_is_a_fraction(tmp_path):
    conf = CLIENT + "offline:\n  enabled: true\n  dim: 4\n"
    with pytest.raises(ConfigError) as e:
        config.load_client_config(write(tmp_path, "client.yaml", conf))
    assert "dim" in str(e.value)


OFFLINE = {
    "message": "Dashboard server unavailable",
    "clock_format": "%H:%M",
    "dim": 0.75,
}


def test_the_offline_screen_works_before_any_frame_arrives(surfaces):
    """A viewer that boots while the server is down is still a clock."""
    from grydgets.client import OfflineScreen

    pygame.font.init()
    screen = OfflineScreen((640, 480), OFFLINE)
    rendered = screen.render(None, "12:34")
    assert rendered.get_size() == (640, 480)
    # The clock and the message are the only light pixels on a black screen.
    assert rendered.get_bounding_rect().height > 0


def test_the_offline_screen_dims_the_last_frame(surfaces):
    from grydgets.client import OfflineScreen

    pygame.font.init()
    frame = pygame.Surface((640, 480))
    frame.fill((200, 200, 200))
    screen = OfflineScreen((640, 480), OFFLINE)
    rendered = screen.render(frame, "12:34")
    # A corner, away from the centred clock and message.
    assert rendered.get_at((5, 5))[0] < 200 * 0.5


def test_the_offline_screen_redims_only_when_the_frame_changes(surfaces):
    from grydgets.client import OfflineScreen

    pygame.font.init()
    screen = OfflineScreen((64, 48), OFFLINE)
    frame = pygame.Surface((64, 48))
    screen.render(frame, "12:34")
    cached = screen._background
    screen.render(frame, "12:35")
    assert screen._background is cached
    screen.render(pygame.Surface((64, 48)), "12:35")
    assert screen._background is not cached


def test_a_long_message_is_shrunk_to_fit(surfaces):
    from grydgets.client import fit_font

    pygame.font.init()
    message = "Dashboard server unavailable"
    assert fit_font(message, 80, 300).size(message)[0] <= 300
