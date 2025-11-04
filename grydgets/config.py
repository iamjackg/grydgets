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
    }
)


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
