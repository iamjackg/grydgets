"""Read secret *names* out of secrets.yaml -- never values.

Used to populate a dropdown so a `!secret` field can be repointed at a
different key without ever loading actual secret values into the page.
"""

import yaml

SECRETS_FILE = "secrets.yaml"


def list_secret_keys(secrets_path=SECRETS_FILE):
    try:
        with open(secrets_path) as f:
            data = yaml.safe_load(f)
    except (FileNotFoundError, OSError, yaml.YAMLError):
        return []
    # A well-formed secrets.yaml is a mapping of name -> value; anything else
    # (empty file, a top-level list/scalar) has no keys to offer.
    if not isinstance(data, dict):
        return []
    return sorted(data.keys())
