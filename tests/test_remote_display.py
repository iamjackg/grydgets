"""Tests for the remote display: config shape, StreamOutput, and the helpers
the frame endpoints are built from.

Run with: uv run --with pytest python -m pytest tests/test_remote_display.py
"""

import os
import queue

import pytest
import voluptuous

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from grydgets import config
from grydgets.config import ConfigError
from grydgets.outputs import create_outputs
from grydgets.outputs.stream import SHUTDOWN, StreamOutput, offer


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text)
    return str(path)


# --- conf.yaml: the server block is configuration, not a switch ----------


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


# --- the stream output ----------------------------------------------------


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
    assert output.current_frame() == (None, None)

    # Still inside the debounce window.
    output.on_frame(red, freshly_rendered=False)
    assert output.current_frame() == (None, None)

    output.debounce = 0
    output.on_frame(red, freshly_rendered=False)
    data, etag = output.current_frame()
    assert data is not None and etag is not None


def test_identical_pixels_keep_their_etag(surfaces):
    """A re-render that changes nothing must not make clients repaint."""
    red, blue = surfaces
    output = StreamOutput(debounce_ms=0)

    output.on_frame(red, freshly_rendered=True)
    output.on_frame(red, freshly_rendered=False)
    _, first = output.current_frame()

    output.on_frame(red, freshly_rendered=True)
    output.on_frame(red, freshly_rendered=False)
    _, again = output.current_frame()
    assert again == first

    output.on_frame(blue, freshly_rendered=True)
    output.on_frame(blue, freshly_rendered=False)
    _, changed = output.current_frame()
    assert changed != first


def test_subscribers_are_told_the_new_etag(surfaces):
    red, blue = surfaces
    output = StreamOutput(debounce_ms=0)
    subscriber = output.subscribe()

    output.on_frame(red, freshly_rendered=True)
    output.on_frame(red, freshly_rendered=False)
    _, etag = output.current_frame()
    assert subscriber.get_nowait() == etag

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


def test_stopping_wakes_every_subscriber(surfaces):
    """A reload replaces the output, so its generators must exit and let their
    clients reconnect to the new one."""
    output = StreamOutput(debounce_ms=0)
    subscribers = [output.subscribe() for _ in range(3)]
    output.stop()
    assert all(s.get_nowait() is SHUTDOWN for s in subscribers)


# --- helpers behind the endpoints ----------------------------------------


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
    assert not etag_matches("abc", "abc")  # unquoted isn't an ETag
    assert not etag_matches(None, "abc")
    assert not etag_matches('"abc"', None)


# --- client.yaml ----------------------------------------------------------


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


# --- the staleness indicator ---------------------------------------------


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
