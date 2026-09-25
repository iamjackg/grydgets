# Authentication

Widgets and providers that make HTTP requests (`rest`, `restimage`, `httpflip`, and providers in `providers.yaml`)
take an `auth` parameter. The same block also works on a [`post` output](conf-yaml.md#post). It takes one of two
methods:

*   `bearer`: a token, sent as `Authorization: Bearer <token>`. Use this for Home Assistant long-lived access tokens
    and most modern APIs.
*   `basic`: a `username` and a `password`, sent with HTTP Basic authentication. Use this for older devices like IP
    cameras or motionEye.

```yaml
auth:
  bearer: !secret my_bearer_token
```

```yaml
auth:
  basic:
    username: myuser
    password: !secret camera_password
```

You'll usually want to keep the token or password in [`secrets.yaml`](secrets-yaml.md), so that the file with the
widgets in it can be shared or committed.
