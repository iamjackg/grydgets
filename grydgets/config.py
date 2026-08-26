import os

import voluptuous
import yaml

from grydgets import theme

__SECRETS = {"main_secrets": {}}


class ConfigError(Exception):
    """A config file is missing, unreadable, or not what it should be.

    Carries a message meant to be shown on its own -- the entry points print
    it and exit rather than letting a traceback out, because every one of
    these is something about the user's files rather than a bug to report.
    """


def describe_read_failure(filename, error):
    """A one-line explanation of why a config file couldn't be read.

    The absolute path is in the message because relative ones are the
    confusing case: ``--config-dir`` chdirs, so "conf.yaml" alone doesn't
    say which conf.yaml was looked for.
    """
    path = os.path.abspath(filename)
    if isinstance(error, FileNotFoundError):
        return f"{filename}: no such file (looked for {path})"
    if isinstance(error, IsADirectoryError):
        return f"{filename}: is a directory, not a file ({path})"
    if isinstance(error, PermissionError):
        return f"{filename}: not readable ({path})"
    return f"{filename}: could not be read ({path}): {error}"


def secret_loader(_, node):
    if not __SECRETS["main_secrets"]:
        try:
            with open("secrets.yaml") as secrets_f:
                secret_data = yaml.load(secrets_f, Loader=yaml.SafeLoader)
        except OSError as e:
            raise ConfigError(
                f"{describe_read_failure('secrets.yaml', e)}, and it is "
                f"needed to resolve '!secret {node.value}'"
            ) from None
        except yaml.YAMLError as e:
            raise ConfigError(f"secrets.yaml is not valid YAML:\n{e}") from None
        if not isinstance(secret_data, dict):
            raise ConfigError("secrets.yaml must be a mapping of name to secret")
        __SECRETS["main_secrets"] = secret_data

    try:
        return __SECRETS["main_secrets"][node.value]
    except KeyError:
        known = ", ".join(sorted(__SECRETS["main_secrets"])) or "nothing"
        raise ConfigError(
            f"'!secret {node.value}' is not in secrets.yaml (it defines: {known})"
        ) from None


yaml.add_constructor("!secret", secret_loader)
theme.register_constructors()


def load_yaml(filename):
    try:
        with open(filename) as conf_f:
            parsed_yaml = yaml.load(conf_f, Loader=yaml.FullLoader)
    except OSError as e:
        raise ConfigError(describe_read_failure(filename, e)) from None
    except yaml.YAMLError as e:
        raise ConfigError(f"{filename} is not valid YAML:\n{e}") from None
    return parsed_yaml


def load_theme_file(filename):
    """Read a theme file: a document whose root *is* a theme block.

    No ``theme:`` key wrapping it, so the file is exactly what you would
    paste under ``theme:`` in the widgets file. A wrapped file is the
    plausible mistake, so it gets told what's wrong rather than being read as
    a theme with one section named "theme".
    """
    document = load_yaml(filename)
    if document is None:
        raise theme.ThemeError(f"{filename} is empty")
    if not isinstance(document, dict):
        raise theme.ThemeError(f"{filename}: a theme file must be a mapping")
    if set(document) == {"theme"}:
        raise theme.ThemeError(
            f"{filename}: a theme file's top level is the theme block itself "
            f"-- remove the 'theme:' key and unindent what's under it"
        )
    return document


def load_widget_config(filename, theme_file=None):
    """Load the widgets file and resolve its theme block.

    Kept separate from :func:`load_yaml` so that conf.yaml and providers.yaml,
    which share the loader, don't pick up theme semantics.

    ``theme_file`` replaces the widgets file's ``theme:`` block outright, so
    the same widget tree can be rendered with a different look without being
    edited. The widgets file's own block is the base theme and stays the one
    that loads when no override is given.
    """
    document = load_yaml(filename)
    if not isinstance(document, dict) or "widgets" not in document:
        raise ConfigError(
            f"{filename} has no top-level 'widgets:' key, so there is no "
            f"dashboard to draw"
        )
    if not isinstance(document["widgets"], list) or not document["widgets"]:
        raise ConfigError(
            f"{filename}: 'widgets:' must be a list holding the one widget "
            f"that fills the screen, usually a grid"
        )
    if theme_file is not None:
        override = load_theme_file(theme_file)
        theme.check_replacement(document.get("theme"), override, theme_file)
        document["theme"] = override
    return theme.apply_theme(document)


# Loopback rather than 0.0.0.0, so a port opened on the config's behalf is not
# also put on the network. Every remote-facing deployment overrides this, and
# cli.py warns when one has not.
DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = 5000


def server_settings(conf):
    """Host, port and tokens for the HTTP server, with defaults filled in.

    ``load_config`` returns the file as written rather than the validated copy,
    so schema defaults never reach it and ``server:`` may be missing entirely.
    """
    server = conf.get("server") or {}
    return {
        "host": server.get("host", DEFAULT_SERVER_HOST),
        "port": server.get("port", DEFAULT_SERVER_PORT),
        "auth": server.get("auth") or {},
    }


# Output sub-schemas
window_output_schema = {
    voluptuous.Required("type"): "window",
    voluptuous.Optional("fullscreen", default=False): bool,
    voluptuous.Optional("x_display"): str,
}

framebuffer_output_schema = {
    voluptuous.Required("type"): "framebuffer",
    voluptuous.Required("device"): str,
}

file_output_schema = {
    voluptuous.Required("type"): "file",
    voluptuous.Optional("output_path", default="./headless_output"): str,
    voluptuous.Optional("render_interval", default=60): voluptuous.All(
        int, voluptuous.Range(min=1)
    ),
    voluptuous.Optional("image_format", default="png"): voluptuous.In(
        ["png", "jpg", "jpeg", "bmp"]
    ),
    voluptuous.Optional("filename_pattern", default="grydgets_{timestamp}"): str,
    voluptuous.Optional("keep_images", default=100): voluptuous.All(
        int, voluptuous.Range(min=0)
    ),
    voluptuous.Optional("create_latest_symlink", default=True): bool,
}

post_output_schema = {
    voluptuous.Required("type"): "post",
    voluptuous.Required("url"): str,
    voluptuous.Optional("image_format", default="png"): voluptuous.In(
        ["png", "jpg", "jpeg", "bmp"]
    ),
    voluptuous.Optional("trigger", default="on_dirty"): voluptuous.In(
        ["on_dirty", "interval"]
    ),
    voluptuous.Optional("min_interval", default=60): voluptuous.All(
        int, voluptuous.Range(min=1)
    ),
    voluptuous.Optional("auth"): {
        voluptuous.Optional("bearer"): str,
        voluptuous.Optional("basic"): {
            voluptuous.Optional("username"): str,
            voluptuous.Optional("password"): str,
        },
    },
    voluptuous.Optional("multipart"): {
        voluptuous.Optional("field_name", default="file"): str,
        voluptuous.Optional("filename", default="image"): str,
    },
    voluptuous.Optional("after_post"): {
        voluptuous.Required("url"): str,
        voluptuous.Optional("method", default="GET"): voluptuous.In(
            ["GET", "POST", "PUT", "DELETE"]
        ),
    },
}


# Frames held in memory and served over the HTTP server rather than pushed
# anywhere. ``debounce_ms`` is how long the tree must hold still before a frame
# is published, so a flip that dirties the tree over many passes costs one
# encode instead of one per pass.
stream_output_schema = {
    voluptuous.Required("type"): "stream",
    voluptuous.Optional("image_format", default="jpeg"): voluptuous.In(
        ["png", "jpg", "jpeg", "bmp"]
    ),
    voluptuous.Optional("debounce_ms", default=200): voluptuous.All(
        int, voluptuous.Range(min=0, max=10000)
    ),
}


# Day/night appearance. The two theme files are named here rather than in the
# widgets file because the coordinates have to live in conf.yaml regardless --
# they are a property of where the screen is, not of what it draws -- and
# splitting one feature across two files would be worse than either.
#
# The coordinates are optional: without them nothing switches on its own and
# the POST /theme endpoint is the only thing that changes the theme, which is
# what you want if something else (a presence sensor, a light sensor, an
# automation) should be making the decision instead of the sun.
appearance_schema = {
    voluptuous.Optional("latitude"): voluptuous.All(
        voluptuous.Coerce(float), voluptuous.Range(min=-90, max=90)
    ),
    voluptuous.Optional("longitude"): voluptuous.All(
        voluptuous.Coerce(float), voluptuous.Range(min=-180, max=180)
    ),
    # Which theme a fresh start puts up: the one used until the endpoint says
    # otherwise, and the one the sun's answer is replaced by on a day it has
    # none (inside a polar circle).
    voluptuous.Optional("default", default="day"): voluptuous.In(["day", "night"]),
    # Named for its consequence: turning it on opens a port. Switching by the
    # sun is a timer in the render loop and needs no server, so a config that
    # only describes an appearance never starts one by accident.
    voluptuous.Optional("http_control", default=False): bool,
    voluptuous.Required("themes"): {
        voluptuous.Required("day"): str,
        voluptuous.Required("night"): str,
    },
    # Minutes, per boundary, so dusk can be brought forward without also
    # delaying the morning. Capped at half a day, past which an offset has
    # stopped meaning "a bit before sunset" and is a typo.
    voluptuous.Optional("offsets"): {
        voluptuous.Optional("sunrise", default=0): voluptuous.All(
            int, voluptuous.Range(min=-720, max=720)
        ),
        voluptuous.Optional("sunset", default=0): voluptuous.All(
            int, voluptuous.Range(min=-720, max=720)
        ),
    },
}


def _validate_appearance(value):
    """Validate ``appearance:``, rejecting half a location.

    One coordinate on its own is always a mistake -- an unfinished edit, or a
    typo in a key name -- and taken at face value it would silently mean
    "manual switching only", which is not what someone who wrote a latitude
    wanted.
    """
    validated = voluptuous.Schema(appearance_schema)(value)
    has = [k for k in ("latitude", "longitude") if k in validated]
    if len(has) == 1:
        missing = "longitude" if has[0] == "latitude" else "latitude"
        raise voluptuous.Invalid(
            f"appearance has a {has[0]} but no {missing}: give both to switch "
            f"themes by the sun, or neither to switch them only over HTTP"
        )
    return validated


def _validate_output(value):
    """Validate a single output entry by dispatching to the right sub-schema."""
    if not isinstance(value, dict) or "type" not in value:
        raise voluptuous.Invalid("Each output must be a dict with a 'type' key")

    schemas = {
        "window": voluptuous.Schema(window_output_schema),
        "framebuffer": voluptuous.Schema(framebuffer_output_schema),
        "file": voluptuous.Schema(file_output_schema),
        "post": voluptuous.Schema(post_output_schema),
        "stream": voluptuous.Schema(stream_output_schema),
    }

    output_type = value["type"]
    if output_type not in schemas:
        raise voluptuous.Invalid(
            f"Unknown output type '{output_type}'. "
            f"Available: {list(schemas.keys())}"
        )

    return schemas[output_type](value)


config_schema = voluptuous.Schema(
    {
        voluptuous.Required("graphics"): {
            voluptuous.Required("fps-limit", default=60): voluptuous.All(
                int, voluptuous.Range(min=1, max=60)
            ),
            voluptuous.Required("fullscreen", default=False): bool,
            voluptuous.Required("resolution"): voluptuous.All(
                [int, voluptuous.Range(min=1)], voluptuous.Length(2)
            ),
            voluptuous.Optional("fb-device"): str,
            voluptuous.Optional("x-display"): str,
            voluptuous.Optional("flip", default=False): bool,
            voluptuous.Optional("smooth-scaling", default=True): bool,
            voluptuous.Optional("text-scale", default=1.0): voluptuous.All(
                voluptuous.Coerce(float), voluptuous.Range(min=0.1, max=10)
            ),
        },
        voluptuous.Required("logging"): {
            voluptuous.Required("level", default="info"): voluptuous.In(
                ["debug", "info", "warning"]
            )
        },
        # Configures the HTTP server but never starts it. Three features do
        # that: a notifiable widget, a stream output, or
        # appearance.http_control. If this block is absent, whichever of those
        # asked for a server gets the defaults below.
        voluptuous.Optional("server"): {
            voluptuous.Optional("host", default=DEFAULT_SERVER_HOST): str,
            voluptuous.Optional("port", default=DEFAULT_SERVER_PORT): voluptuous.All(
                int, voluptuous.Range(1, 655355)
            ),
            voluptuous.Optional("auth"): {
                voluptuous.Optional("stream_token"): str,
                voluptuous.Optional("control_token"): str,
            },
        },
        # Legacy headless config (still accepted, migrated to file output)
        voluptuous.Optional("headless"): {
            voluptuous.Required("enabled", default=False): bool,
            voluptuous.Required("output_path", default="./headless_output"): str,
            voluptuous.Required("render_interval", default=60): voluptuous.All(
                int, voluptuous.Range(min=1)
            ),
            voluptuous.Required("image_format", default="png"): voluptuous.In(
                ["png", "jpg", "jpeg", "bmp"]
            ),
            voluptuous.Optional("filename_pattern", default="grydgets_{timestamp}"): str,
            voluptuous.Optional("keep_images", default=100): voluptuous.All(
                int, voluptuous.Range(min=0)
            ),
            voluptuous.Optional("create_latest_symlink", default=True): bool,
        },
        # New outputs config
        voluptuous.Optional("outputs"): [_validate_output],
        # Day/night theme switching. Absent means one theme, all day.
        voluptuous.Optional("appearance"): _validate_appearance,
    }
)


def migrate_config(conf):
    """Translate legacy config to new outputs-based config.

    If 'outputs' key is present, use it directly.
    Otherwise, synthesize outputs from graphics + headless keys.
    """
    if "outputs" in conf:
        return conf

    outputs = []
    graphics = conf.get("graphics", {})
    headless = conf.get("headless", {})

    if headless.get("enabled", False):
        file_conf = {k: v for k, v in headless.items() if k != "enabled"}
        file_conf["type"] = "file"
        outputs.append(file_conf)
    elif "fb-device" in graphics:
        outputs.append({
            "type": "framebuffer",
            "device": graphics["fb-device"],
        })
    else:
        output = {
            "type": "window",
            "fullscreen": graphics.get("fullscreen", False),
        }
        if "x-display" in graphics:
            output["x_display"] = graphics["x-display"]
        outputs.append(output)

    conf["outputs"] = outputs
    return conf


# Provider configuration schema
provider_auth_schema = voluptuous.Schema(
    voluptuous.Any(
        {
            voluptuous.Required("type"): voluptuous.In(["basic", "bearer"]),
            voluptuous.Optional("username"): str,
            voluptuous.Optional("password"): str,
            voluptuous.Optional("token"): str,
        },
        {
            voluptuous.Optional("basic"): {
                voluptuous.Optional("username"): str,
                voluptuous.Optional("password"): str,
            },
            voluptuous.Optional("bearer"): str,
        }
    )
)

provider_schema = voluptuous.Schema(
    {
        voluptuous.Required("providers"): {
            str: {
                voluptuous.Required("type"): voluptuous.In(["rest"]),
                voluptuous.Required("url"): str,
                voluptuous.Optional("method", default="GET"): voluptuous.In(
                    ["GET", "POST", "PUT", "DELETE"]
                ),
                voluptuous.Optional("headers"): dict,
                voluptuous.Optional("params"): dict,
                voluptuous.Optional("body"): voluptuous.Any(dict, str),
                voluptuous.Optional("payload"): voluptuous.Any(dict, str),
                voluptuous.Optional("auth"): provider_auth_schema,
                voluptuous.Optional("json_path"): str,
                voluptuous.Optional("jq_expression"): str,
                voluptuous.Optional("update_interval", default=60): voluptuous.All(
                    int, voluptuous.Range(min=1)
                ),
                voluptuous.Optional("jitter", default=0): voluptuous.All(
                    int, voluptuous.Range(min=0)
                ),
            }
        }
    }
)


def _validate(schema, conf_data, filename):
    """Run a voluptuous schema, reporting a failure as a :class:`ConfigError`.

    voluptuous's own message says what's wrong and where ("required key not
    provided @ data['server']"); all this adds is which file it's about.
    """
    try:
        return schema(conf_data)
    except voluptuous.Invalid as e:
        raise ConfigError(f"{filename} is not valid: {e}") from None


def load_config(filename):
    conf_data = load_yaml(filename)
    theme.reject_tokens(conf_data, filename)
    _validate(config_schema, conf_data, filename)

    return conf_data


# --- client.yaml ---------------------------------------------------------
#
# The remote frame viewer's entire configuration. A separate file rather than a
# mode of conf.yaml, so a viewer machine's config directory holds one file and
# no keys that silently do nothing.

# Only outputs that put a frame on a screen. A viewer that fetched frames to
# write them to disk or POST them elsewhere would be a relay, which is not what
# this is for.
CLIENT_OUTPUT_TYPES = ("window", "framebuffer")


def _validate_client_output(value):
    if not isinstance(value, dict) or "type" not in value:
        raise voluptuous.Invalid("Each output must be a dict with a 'type' key")
    schemas = {
        "window": voluptuous.Schema(window_output_schema),
        "framebuffer": voluptuous.Schema(framebuffer_output_schema),
    }
    output_type = value["type"]
    if output_type not in schemas:
        raise voluptuous.Invalid(
            f"Unknown client output type '{output_type}'. "
            f"Available: {list(schemas.keys())}"
        )
    return schemas[output_type](value)


client_schema = voluptuous.Schema(
    {
        voluptuous.Required("server"): {
            voluptuous.Required("url"): str,
            voluptuous.Optional("token"): str,
            # Seconds to wait before reconnecting after a dropped connection.
            # A rejected token backs off much harder on its own.
            voluptuous.Optional("reconnect_delay", default=2): voluptuous.All(
                voluptuous.Coerce(float), voluptuous.Range(min=0.1, max=3600)
            ),
            # How long the connection must stay down before the staleness
            # indicator appears, so a two-second reconnect does not flash one.
            voluptuous.Optional("stale_after", default=30): voluptuous.All(
                voluptuous.Coerce(float), voluptuous.Range(min=1, max=86400)
            ),
        },
        voluptuous.Required("graphics"): {
            voluptuous.Required("resolution"): voluptuous.All(
                [int, voluptuous.Range(min=1)], voluptuous.Length(2)
            ),
        },
        voluptuous.Optional("logging", default={"level": "info"}): {
            voluptuous.Required("level", default="info"): voluptuous.In(
                ["debug", "info", "warning"]
            )
        },
        voluptuous.Optional(
            "indicator", default={"corner": "bottom-right"}
        ): {
            voluptuous.Optional("corner", default="bottom-right"): voluptuous.In(
                ["top-left", "top-right", "bottom-left", "bottom-right"]
            ),
        },
        voluptuous.Required("outputs"): voluptuous.All(
            [_validate_client_output], voluptuous.Length(min=1, max=1)
        ),
    }
)


def load_client_config(filename):
    """Load and validate client.yaml.

    Unlike :func:`load_config`, this returns the validated document, so the
    client reads the schema's defaults.
    """
    conf_data = load_yaml(filename)
    theme.reject_tokens(conf_data, filename)
    return _validate(client_schema, conf_data, filename)


def load_providers_config(filename):
    """Load and validate provider configuration.

    Args:
        filename: Path to providers configuration file

    Returns:
        Validated provider configuration dict
    """
    conf_data = load_yaml(filename)
    theme.reject_tokens(conf_data, filename)
    _validate(provider_schema, conf_data, filename)

    return conf_data
