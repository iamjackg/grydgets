# Data extraction: `json_path` and `jq_expression`

Widgets and providers that read JSON can pull a value out of the response in two ways. Both work in:

*   the REST widgets: `rest`, `restimage`, `httpflip`
*   providers in [`providers.yaml`](providers-yaml.md)
*   the provider widgets: `provider`, `providerflip`, `providerimage`, `providerbarchart` (which call the path
    `data_path` instead of `json_path`)

## `json_path`

A path to a single value, written the way you'd walk the parsed JSON in Python: dots for keys and square brackets
for list indexes. This is all you need most of the time.

```yaml
json_path: "events[0].title"      # the title of the first event
json_path: "user.address.city"    # nested objects
```

## `jq_expression`

A [jq](https://jqlang.github.io/jq/) expression, for when you need to filter, transform or format the data rather
than just pick a value out of it.

```yaml
jq_expression: '.events[] | select(.priority == "high")'                # filter
jq_expression: '.items | map(.name) | join(", ")'                       # transform
jq_expression: '.[0].date | strptime("%Y-%m-%d") | strftime("%B %d")'   # format
```

## Using both

If you set both, `json_path` is applied first and jq runs on its result. That way you can narrow the data down with a
simple path and keep the jq expression short.

```yaml
json_path: "events"                                   # the events list
jq_expression: 'map(select(.active)) | .[0].title'    # the first active one's title
```
