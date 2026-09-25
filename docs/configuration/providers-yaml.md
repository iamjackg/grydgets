# Data providers (`providers.yaml`)

A provider fetches data in the background and makes it available to any number of widgets, so you don't have to
call the same API once per widget. For example, if you have a widget for each day of the week's forecast, a single
provider can fetch the whole forecast once and share it with all seven of them.

Widgets read from a provider by name, using the [provider widgets](../widgets/provider-widgets.md). Providers are
configured in `providers.yaml`:

```yaml
providers:
  hass_calendar:
    type: rest
    url: !secret hass_calendar_url
    headers:
      Authorization: !secret hass_bearer_token
    json_path: "events"                                  # keep only the events list
    jq_expression: 'map(select(.status == "active"))'    # and only the active ones
    update_interval: 60                                  # fetch every 60 seconds
    jitter: 5                                            # plus a random 0-5 second delay

  weather_api:
    type: rest
    url: https://api.weather.com/current
    method: GET
    auth:
      bearer: !secret weather_token
    update_interval: 300
```

## When you'd want this

Use a provider when more than one widget shows data from the same response, like several fields of a weather report
or several events from a calendar. If a value is only shown in one place, a `rest` widget that makes its own request
is simpler.

Providers are also the only way to feed a [`providerbarchart`](../widgets/provider-widgets.md#providerbarchart).

## Options

*   `type`: Provider type. Only `rest` is supported for now.
*   `url`: The URL to fetch from.
*   `method` _(optional)_: HTTP method (`GET`, `POST`, `PUT`, `DELETE`). Defaults to `GET`.
*   `headers` _(optional)_: A mapping of HTTP headers to send.
*   `params` _(optional)_: A mapping of query parameters to add to the URL.
*   `body` or `payload` _(optional)_: A JSON request body, sent with `POST` and `PUT` requests. The two names do the
    same thing.
*   `auth` _(optional)_: A bearer token or a username and password, see [Authentication](authentication.md).
*   `json_path` _(optional)_: A path to the part of the response to keep, like `"events[0].title"`. See [Data
    extraction](data-extraction.md).
*   `jq_expression` _(optional)_: A jq expression to filter or transform the response, like
    `'.events[] | select(.active)'`. If you also set `json_path`, it's applied first, and the jq expression runs on
    its result.
*   `update_interval` _(optional)_: Seconds between fetches. Defaults to `60`.
*   `jitter` _(optional)_: Adds a random delay of up to this many seconds to each fetch. If you have several providers
    with the same interval, this stops them from all hitting the network at the same moment. Defaults to `0`.

Keep in mind that whatever you extract here is what every widget reading from the provider gets. If different
widgets need different parts of the response, keep the provider's extraction broad and let each widget pick its own
part with `data_path` or `jq_expression`.
