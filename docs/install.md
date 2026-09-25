# Install

You'll need Python 3.9 or newer. The easiest way to install Grydgets is with [uv](https://docs.astral.sh/uv/), which
takes care of the Python environment for you. If you don't have it yet, follow the [uv installation
instructions](https://docs.astral.sh/uv/getting-started/installation/) first, or use the pip instructions below.

## From source (recommended for Raspberry Pi)

=== "uv"

    ```bash
    git clone https://github.com/iamjackg/grydgets
    cd grydgets
    uv tool install .
    ```

    This installs the `grydgets` command, along with `grydgets-client` and `grydgets-editor`, so you can run it from
    any directory. If uv warns you that its tool directory isn't on your `PATH`, run `uv tool update-shell` and open a
    new terminal.

    To update an existing installation:

    ```bash
    cd grydgets
    git pull
    uv tool install --reinstall .
    ```

=== "pip"

    ```bash
    git clone https://github.com/iamjackg/grydgets
    cd grydgets
    python3 -m venv venv
    venv/bin/pip install .
    ```

    This installs the `grydgets`, `grydgets-client` and `grydgets-editor` commands into `venv/bin`. Either run them
    from there, or activate the virtualenv with `source venv/bin/activate` so they're on your `PATH`.

    To update an existing installation:

    ```bash
    cd grydgets
    git pull
    venv/bin/pip install .
    ```

If you run `grydgets` now, it will complain that there's no `conf.yaml`. That's expected: you'll write one in [Your
first dashboard](tutorial.md). If you'd rather start from a working example, the repository includes
`conf.yaml.sample` and `widgets.yaml.sample`: copy them to `conf.yaml` and `widgets.yaml` and edit from there.

You can also run `python main.py` from the repository if you'd rather not install the package, as long as the
dependencies are installed in that Python.

## Docker (headless mode)

The repository includes a Dockerfile and a docker-compose configuration, in case you want to run Grydgets without a
screen and save the dashboard to disk instead.

1. Create a `data/` directory with your configuration files, fonts, and images:

```
data/
├── conf.yaml
├── widgets.yaml
├── providers.yaml
├── secrets.yaml  # optional
├── myfont.ttf    # any custom fonts referenced in widgets.yaml
└── images/       # any images referenced in widgets.yaml
    └── logo.jpg
```

2. Make sure `conf.yaml` has a file output configured (see [Outputs](configuration/conf-yaml.md#outputs)).

3. Start the container:

```bash
docker compose up -d
```

Rendered images are saved to `data/headless_output/`, and the notification endpoint is exposed on port 5000.

## Command-line options

```
grydgets [--widgets FILE] [--theme FILE] [--config-dir DIR]
```

*   `--widgets`: Widget configuration file. Defaults to `widgets.yaml`.
*   `--theme`: A [theme file](theming.md#theme-files) to use instead of the widgets file's own `theme:` block. Using this turns off [day/night switching](configuration/conf-yaml.md#appearance-day-and-night-themes) if `conf.yaml` configures it.
*   `--config-dir`: Directory containing config files, fonts, and images. All relative paths are resolved from here. Defaults to the current working directory.

The package also installs two other commands: `grydgets-client` shows a dashboard that's rendered on another machine
(see [Remote displays](remote-displays.md)), and `grydgets-editor` starts the [widget editor](widget-editor.md).
