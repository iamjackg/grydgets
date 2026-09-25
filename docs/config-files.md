# How the config files fit together

Grydgets is configured through a handful of YAML files. It looks for them in the current
directory, or in a directory passed with `--config-dir`. Fonts and images referenced from
`widgets.yaml` are resolved from the same place.

Two of the files are mandatory.

**`conf.yaml`** describes how to run Grydgets on this machine: the resolution, where the rendered
dashboard goes (a window, a file, another machine), and various options for the HTTP
server used by some features. If you move the same dashboard to a different screen or device, this is the file you'll need to change. See [`conf.yaml`](configuration/conf-yaml.md).

**`widgets.yaml`** describes the dashboard itself: the tree of widgets, how they're laid out, and
where they each get their data from. See [widgets.yaml](configuration/widgets-yaml.md) and [Widgets](widgets/index.md).

The other two are optional.

**`secrets.yaml`** (inspired by the same pattern as Home Assistant) is meant to contain tokens, passwords and URLs you'd rather not commit. Other files can refer to them with `!secret`. See [secrets.yaml](configuration/secrets-yaml.md).

**`providers.yaml`** defines data sources that are fetched once and shared by multiple widgets. Normal `rest` widgets make their own HTTP request, so if you had seven widgets showing seven days of a forecast they would make seven identical calls.
Using a provider makes the call once and hands the forecast response to all of them. You only need this file if more than one widget reads from the same response from the same API. See [providers.yaml](configuration/providers-yaml.md).

There's also a fifth kind of file, the theme file. A theme can override colours, fonts and sizes in
`widgets.yaml`, so you can change the look of the dashboard without touching the layout. Grydgets can also automatically switch between day and night themes using this mechanism. See [Theming](theming.md).

Sample `conf.yaml` and `widgets.yaml` files are included in the repository to get you started.

## Which file does what

| I want to | Edit |
|---|---|
| Change the resolution, or run fullscreen | `conf.yaml` |
| Send the dashboard somewhere other than a window | `conf.yaml` |
| Add, remove or rearrange widgets | `widgets.yaml` |
| Point a widget at a different URL | `widgets.yaml`, or `providers.yaml` if it's shared |
| Change colours, fonts or sizes | the `theme:` block, or a theme file |
| Keep a token out of git | `secrets.yaml` |
