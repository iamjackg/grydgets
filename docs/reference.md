# Reference

## Command-line options

```
grydgets [--widgets FILE] [--theme FILE] [--config-dir DIR]
```

*   `--widgets`: Widget configuration file. Defaults to `widgets.yaml`.
*   `--theme`: A [theme file](theming.md#theme-files) to use instead of the widgets file's own `theme:` block. Using this turns off [day/night switching](configuration/conf-yaml.md#appearance-day-and-night-themes) if `conf.yaml` configures it.
*   `--config-dir`: Directory containing config files, fonts, and images. All relative paths are resolved from here. Defaults to the current working directory.

`grydgets-client` shows a dashboard that's rendered on another machine (see [Remote
displays](remote-displays.md)), and `grydgets-editor` starts the [widget editor](widget-editor.md).

## HTTP endpoints

The server is only started if at least one of these features is in use. See [`server`](configuration/conf-yaml.md#server).

| Endpoint | What uses it |
|---|---|
| `/notify` | [Push widgets](widgets/push-widgets.md) |
| `/frame`, `/events` | The [`stream` output](configuration/conf-yaml.md#stream) |
| `/theme` | [`appearance.http_control: true`](theming.md#setting-the-theme-over-http) |

## Signals

*   `SIGUSR1`: [reload](hot-reload.md) `conf.yaml`, `widgets.yaml`, `providers.yaml` and the theme files.

## `schema.json`

`schema.json` in the repository root is a [JSON Schema](https://json-schema.org/) for `widgets.yaml`. If you point
your editor at it, you'll get completion and validation for every widget and parameter while you type. With the YAML
language server (used by VS Code's YAML extension, among others), add this line at the top of `widgets.yaml`:

```yaml
# yaml-language-server: $schema=./schema.json
```
