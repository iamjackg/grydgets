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


def load_config(filename):
    conf_data = load_yaml(filename)
    config_schema(conf_data)

    return conf_data
