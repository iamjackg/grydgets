"""Tests for grydgets/config.py's file loading and its error messages.

Every failure here is something about the user's files rather than a bug, so
each one has to arrive as a ConfigError carrying a message worth printing on
its own -- the entry points show it and exit instead of raising.

Run with: uv run --with pytest python -m pytest test_config.py
"""

import pytest

from grydgets import config
from grydgets.config import ConfigError

WIDGETS = "widgets: [{widget: text, text: hello}]\n"

CONF = """
graphics:
  resolution: [1366, 768]
  fps-limit: 10
logging:
  level: info
server:
  port: 5000
"""


@pytest.mark.parametrize(
    "load, name",
    [
        (config.load_widget_config, "widgets.yaml"),
        (config.load_config, "conf.yaml"),
        (config.load_providers_config, "providers.yaml"),
        (config.load_theme_file, "theme.yaml"),
    ],
)
def test_a_missing_file_says_where_it_looked(tmp_path, load, name):
    path = tmp_path / name
    with pytest.raises(ConfigError) as excinfo:
        load(str(path))
    message = str(excinfo.value)
    assert "no such file" in message
    # The absolute path, because --config-dir means the relative one is
    # ambiguous about which directory was searched.
    assert str(path) in message


def test_a_directory_is_not_mistaken_for_a_missing_file(tmp_path):
    (tmp_path / "widgets.yaml").mkdir()
    with pytest.raises(ConfigError) as excinfo:
        config.load_widget_config(str(tmp_path / "widgets.yaml"))
    assert "is a directory" in str(excinfo.value)


def test_an_unreadable_file_says_so(tmp_path):
    path = tmp_path / "conf.yaml"
    path.write_text(CONF)
    path.chmod(0o000)
    try:
        with pytest.raises(ConfigError) as excinfo:
            config.load_config(str(path))
        assert "not readable" in str(excinfo.value)
    finally:
        path.chmod(0o644)


def test_broken_yaml_names_the_file_and_keeps_the_parser_detail(tmp_path):
    path = tmp_path / "widgets.yaml"
    path.write_text("widgets:\n  - widget: text\n   text: bad indent\n")
    with pytest.raises(ConfigError) as excinfo:
        config.load_widget_config(str(path))
    message = str(excinfo.value)
    assert "widgets.yaml is not valid YAML" in message
    assert "line 3" in message


@pytest.mark.parametrize(
    "body, expected",
    [
        ("theme:\n  colors: {}\n", "no top-level 'widgets:' key"),
        ("- a\n- b\n", "no top-level 'widgets:' key"),
        ("widgets: []\n", "must be a list holding the one widget"),
        ("widgets: not-a-list\n", "must be a list holding the one widget"),
    ],
)
def test_a_widgets_file_with_no_tree_is_reported(tmp_path, body, expected):
    """cli.py reads widgets[0] straight off the document; without this the
    failure is a KeyError or IndexError from deep inside startup."""
    path = tmp_path / "widgets.yaml"
    path.write_text(body)
    with pytest.raises(ConfigError) as excinfo:
        config.load_widget_config(str(path))
    assert expected in str(excinfo.value)


def test_a_schema_failure_names_the_file(tmp_path):
    path = tmp_path / "conf.yaml"
    path.write_text("graphics:\n  resolution: [1366, 768]\n  fps-limit: 10\n")
    with pytest.raises(ConfigError) as excinfo:
        config.load_config(str(path))
    message = str(excinfo.value)
    assert "conf.yaml is not valid" in message
    # voluptuous' own text says which key, and that's worth keeping.
    assert "logging" in message or "server" in message


def test_a_good_pair_of_files_still_loads(tmp_path):
    (tmp_path / "widgets.yaml").write_text(WIDGETS)
    (tmp_path / "conf.yaml").write_text(CONF)
    assert config.load_widget_config(str(tmp_path / "widgets.yaml"))["widgets"]
    assert config.load_config(str(tmp_path / "conf.yaml"))["server"]["port"] == 5000


@pytest.fixture
def fresh_secrets(monkeypatch, tmp_path):
    """secrets.yaml is read relative to the cwd and memoised; clear both."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(getattr(config, "__SECRETS"), "main_secrets", {})
    return tmp_path


def test_a_missing_secrets_file_names_the_secret_that_needed_it(fresh_secrets):
    (fresh_secrets / "widgets.yaml").write_text(
        "widgets: [{widget: rest, auth: {bearer: !secret hass_token}}]\n"
    )
    with pytest.raises(ConfigError) as excinfo:
        config.load_widget_config(str(fresh_secrets / "widgets.yaml"))
    message = str(excinfo.value)
    assert "secrets.yaml: no such file" in message
    assert "!secret hass_token" in message


def test_an_unknown_secret_lists_the_ones_that_exist(fresh_secrets):
    (fresh_secrets / "secrets.yaml").write_text("hass_token: shhh\nother: x\n")
    (fresh_secrets / "widgets.yaml").write_text(
        "widgets: [{widget: rest, auth: {bearer: !secret hass_tokne}}]\n"
    )
    with pytest.raises(ConfigError) as excinfo:
        config.load_widget_config(str(fresh_secrets / "widgets.yaml"))
    message = str(excinfo.value)
    assert "hass_tokne" in message
    assert "hass_token, other" in message


def test_a_secret_that_is_there_still_resolves(fresh_secrets):
    (fresh_secrets / "secrets.yaml").write_text("hass_token: shhh\n")
    (fresh_secrets / "widgets.yaml").write_text(
        "widgets: [{widget: rest, auth: {bearer: !secret hass_token}}]\n"
    )
    doc = config.load_widget_config(str(fresh_secrets / "widgets.yaml"))
    assert doc["widgets"][0]["auth"]["bearer"] == "shhh"
