# Widget editor

!!! warning "This is highly experimental"

    The editor works for the common edits, but it's still rough: the forms only cover what's in the schema, error
    handling is thin in places, and the UI hasn't had much polish. Keep a copy of your `widgets.yaml` somewhere, and
    expect to open it in a text editor for anything complicated.

The widget editor is a local, browser-based editor for `widgets.yaml`. You can browse the widget tree, add, remove and
reorder the children of container widgets, and edit each widget's properties through forms generated from
`schema.json`, all without touching the YAML by hand.

```bash
grydgets-editor --widgets widgets.yaml
```

Then open `http://127.0.0.1:5050/` in a browser. Options:

| Flag | Default | Purpose |
|---|---|---|
| `--widgets` | `widgets.yaml` | file to edit |
| `--host` | `127.0.0.1` | bind address |
| `--port` | `5050` | bind port |
| `--debug` | off | Flask debug mode |

## Saving

The editor only reads and writes the widgets file you point it at. It isn't connected to a running dashboard, so
after saving you'll need to reload the dashboard yourself (see [Hot reload](hot-reload.md)).

Every save writes a timestamped backup (`widgets.yaml-YYYYMMDDHHMM.backup`) before overwriting the file. Schema
violations are shown as warnings when you save, but they never stop you from saving.

## Secrets and theme tokens

`!secret` values, and any field that contains one (like `auth.bearer`), are shown read-only. You can't edit them
through the editor.

Theme tokens are kept as they are when you edit a widget. Color, font path, image path and numeric fields have a
**value / theme** switch, so you can either pick an entry from the matching theme section (`!color panel`,
`!font bold`, `!image screen`, `!size radius`) or type a plain value. A token on any other kind of field is shown as
written and left alone. The same goes for the screen's own `background_image` and `background_color`.

A field that gets its value from [`theme.defaults`](theming.md) is shown grayed out, along with the entry it came
from (`from theme: text-like`) and the value it resolves to. **Override** copies that value onto the widget so you
can edit it there, and **remove** drops the override and goes back to the theme default. Defaults are never written
to the file.

## Testing requests

`rest` and `restimage` widgets have a **Test request** button in their inspector. It runs the widget's actual
request, with `!secret` values, theme tokens and defaults resolved (secrets are redacted in the panel), and shows you
the status code, the raw response, the extracted value and the final value. It's the quickest way to get
`json_path`, `jq_expression` and `format_string` right against live data. For a `rest` widget you can also tweak the
extraction and run it again against the response you already have, without making another request.

!!! warning "Testing sends a real request"

    Testing a `POST`, `PUT` or `PATCH` widget sends a real request to the endpoint, so if that request
    changes something on the other end, it'll change it for real. The panel warns you before doing so.

Provider widgets can't be tested this way, since they don't make their own HTTP requests.
