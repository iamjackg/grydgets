import voluptuous
import yaml

__SECRETS = {"main_secrets": {}}


def secret_loader(_, node):
    if not __SECRETS["main_secrets"]:
        with open("secrets.yaml") as secrets_f:
            secret_data = yaml.load(secrets_f, Loader=yaml.SafeLoader)
            __SECRETS["main_secrets"] = secret_data

    return __SECRETS["main_secrets"][node.value]


yaml.add_constructor("!secret", secret_loader)


def load_yaml(filename):
    with open(filename) as conf_f:
        parsed_yaml = yaml.load(conf_f, Loader=yaml.FullLoader)
    return parsed_yaml


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


def _validate_output(value):
    """Validate a single output entry by dispatching to the right sub-schema."""
    if not isinstance(value, dict) or "type" not in value:
        raise voluptuous.Invalid("Each output must be a dict with a 'type' key")

    schemas = {
        "window": voluptuous.Schema(window_output_schema),
        "framebuffer": voluptuous.Schema(framebuffer_output_schema),
        "file": voluptuous.Schema(file_output_schema),
        "post": voluptuous.Schema(post_output_schema),
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
        },
        voluptuous.Required("logging"): {
            voluptuous.Required("level", default="info"): voluptuous.In(
                ["debug", "info", "warning"]
            )
        },
        voluptuous.Required("server"): {
            voluptuous.Optional("port", default=5000): voluptuous.All(
                int, voluptuous.Range(1, 655355)
            )
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


def load_config(filename):
    conf_data = load_yaml(filename)
    config_schema(conf_data)

    return conf_data


def load_providers_config(filename):
    """Load and validate provider configuration.

    Args:
        filename: Path to providers configuration file

    Returns:
        Validated provider configuration dict
    """
    conf_data = load_yaml(filename)
    provider_schema(conf_data)

    return conf_data
