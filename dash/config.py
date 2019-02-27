import yaml

__SECRETS = {'main_secrets': {}}


def secret_loader(_, node):
    if not __SECRETS['main_secrets']:
        with open('secrets.yaml') as secrets_f:
            secret_data = yaml.load(secrets_f)
            __SECRETS['main_secrets'] = secret_data

    return __SECRETS['main_secrets'][node.value]


yaml.add_constructor('!secret', secret_loader)


def parse_conf(filename):
    with open(filename) as conf_f:
        conf = yaml.load(conf_f)
    return conf
