# Secrets (`secrets.yaml`)

`secrets.yaml` holds tokens, passwords and URLs that you'd rather not have in the rest of your configuration. Any
value in the other configuration files (including a remote display's `client.yaml`) can refer to one of them with
the `!secret` tag:

```yaml title="secrets.yaml"
hass_token: "your_secret_token_here"
api_key: "your_api_key"
```

```yaml
# any other configuration file
auth:
  bearer: !secret hass_token
```

This way, you can share your dashboard or commit it to version control without giving away your tokens. Just make
sure `secrets.yaml` itself stays out of the repository, for example by adding it to `.gitignore`.
