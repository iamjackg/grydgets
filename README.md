# Grydgets

Grydgets draws widget-based dashboards that update in real time, showing local and online data. It runs on anything
that supports Python, PyGame, and SDL, from the oldest Raspberry Pi to a full-blown modern PC.

![](images/grydgets-window.png)

_Note:_ while the vast majority of the codebase was originally written by me, my free time has been dwindling more and more. Recent changes have been almost entirely developed with Claude Code. I have reviewed and tested the output, and I am using Grydgets myself 24/7.

## Installation

### From source (recommended for Raspberry Pi)

```bash
git clone https://github.com/iamjackg/grydgets
cd grydgets

# uv (recommended)
uv sync
uv run grydgets

# pip
python3 -m venv venv
venv/bin/pip install .
venv/bin/grydgets
```

To update an existing installation:

```bash
git pull
uv sync          # or: venv/bin/pip install .
```

You can also run `python main.py` directly if you'd rather not install the package.

### Docker (headless mode)

A Dockerfile and a docker-compose configuration are included for running Grydgets without a screen.

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

2. Make sure `conf.yaml` has a file output configured (see [Outputs](#outputs)).

3. Start the container:

```bash
docker compose up -d
```

Rendered images are saved to `data/headless_output/`, and the notification endpoint is exposed on port 5000.

### Command-line options

```
grydgets [--widgets FILE] [--theme FILE] [--config-dir DIR]
```

*   `--widgets`: Widget configuration file. Defaults to `widgets.yaml`.
*   `--theme`: A [theme file](#theme-files) to use instead of the widgets file's own `theme:` block. Using this turns off [day/night switching](#appearance-day-and-night-themes) if `conf.yaml` configures it.
*   `--config-dir`: Directory containing config files, fonts, and images. All relative paths are resolved from here. Defaults to the current working directory.

`grydgets-client` displays a dashboard rendered on another machine. See
[Remote displays](#remote-displays).

## Configuration

Grydgets is configured through a handful of YAML files. Two of them are
required:

*   `conf.yaml` describes how Grydgets runs on this machine: the resolution,
    where the rendered dashboard goes (a window, a framebuffer, a file, another
    machine), and various options for the HTTP server. See
    [`conf.yaml`](#confyaml).
*   `widgets.yaml` describes the dashboard itself: the tree of widgets, how
    they're laid out, and where each one gets its data from. See
    [Dashboard layout options](#dashboard-layout-options-widgetsyaml) and
    [Widgets](#widgets).

The other ones are optional:

*   `secrets.yaml` can have your tokens and passwords, so that they can be referenced
    from the other files with `!secret` and kept out of version control. See
    [Secrets Management](#secrets-secretsyaml).
*   `providers.yaml` defines data sources that are fetched once and shared by
    several widgets. You only really need it if more than one widget reads from the
    same API. See [Data Providers](#data-providers-providersyaml).
*   Theme files can override the colours, fonts and sizes used in `widgets.yaml`, so
    that you can swap the look of the dashboard without touching the layout, or
    switch between a day and a night theme automatically. See
    [Theming](#theming).

All of these are looked for in the current directory, or in the directory
passed with `--config-dir`. Fonts and images referenced from `widgets.yaml` are
resolved from the same place. Sample `conf.yaml` and `widgets.yaml` files are
included in the repository to get you started.

### `conf.yaml`

Every top-level key of `conf.yaml` is described below. `graphics` and
`logging` are required, the others are optional.

#### `graphics`

The `graphics:` block controls how the dashboard is drawn.

```yaml
graphics:
  fps-limit: 10
  resolution: [480, 320]
  smooth-scaling: true
  flip: false
  text-scale: 1.0
```

*   `fps-limit`: Maximum frames per second. Defaults to `60`.
*   `resolution`: Screen resolution as `[width, height]`.
*   `smooth-scaling` _(optional)_: Use bilinear filtering when scaling images (`true`, the default) or the faster but uglier nearest-neighbour (`false`). Set it to `false` on slow hardware like a Raspberry Pi 2.
*   `flip` _(optional)_: Rotates the output 180 degrees. Defaults to `false`.
*   `text-scale` _(optional)_: A multiplier applied to every text size in `widgets.yaml`, see below. Defaults to `1.0`.

**Using the same widgets file on two screens.** `text_size` for the various widgets is specified in pixels, so using the same value on screens with different resolutions might look wonky. By using `text-scale` in `conf.yaml`, you can use the same `widgets.yaml` on multiple screens and only change the scale. Set it to the height of the screen divided by the height the widgets were designed for. For example, widgets written for a 768
pixel tall screen need `1.4` on a 1080p one:

```yaml
graphics:
  resolution: [1920, 1080]
  text-scale: 1.4
```

Only `text_size` is scaled. Any widget without a
specified `text_size` auto-fits its contents, which already grows with the
resolution. `padding` and `corner_radius` are not affected.

#### `logging`

The `logging:` block controls how much Grydgets writes to the log.

```yaml
logging:
  level: info
```

*   `level`: `debug`, `info`, or `warning`. Defaults to `info`.

#### `outputs`

Outputs determine where the rendered dashboard goes: a window, a framebuffer, a file on disk, or another machine. You can configure one or more of them with an `outputs` list in `conf.yaml`:

```yaml
outputs:
  - type: window
    fullscreen: true
```

If no `outputs` key is present, Grydgets falls back to legacy behavior based on the `graphics` and `headless` keys (see [Legacy Configuration](#legacy-configuration)).

**Rules:**
- At most one display output (`window` or `framebuffer`)
- Any number of non-display outputs (`file`, `post`, `stream`)
- At least one output is required
- If there is no display output, Grydgets doesn't need a screen at all and can run on a headless machine

##### window

Displays the dashboard in an SDL window.

*   `fullscreen` _(optional)_: Run in fullscreen mode. Defaults to `false`.
*   `x_display` _(optional)_: The X display to use (e.g. `":0"`). You only need this if you're starting Grydgets over SSH.

```yaml
outputs:
  - type: window
    fullscreen: true
    x_display: ":0"
```

##### framebuffer

Renders directly to a Linux framebuffer device (e.g. SPI screens on Raspberry Pi).

*   `device`: Path to the framebuffer device (e.g. `"/dev/fb1"`).

```yaml
outputs:
  - type: framebuffer
    device: /dev/fb1
```

##### file

Saves a rendered image to disk at a regular interval. Useful if you want to serve the dashboard from a web server, or to make a timelapse.

*   `output_path` _(optional)_: Directory for saved images. Defaults to `"./headless_output"`.
*   `render_interval` _(optional)_: Seconds between saves. Defaults to `60`.
*   `image_format` _(optional)_: `png`, `jpg`, `jpeg`, or `bmp`. Defaults to `"png"`.
*   `filename_pattern` _(optional)_: Pattern with `{timestamp}` and `{sequence}` placeholders. Defaults to `"grydgets_{timestamp}"`.
*   `keep_images` _(optional)_: Keep the last N images, deleting older ones. `0` = unlimited. Defaults to `100`.
*   `create_latest_symlink` _(optional)_: Create a `latest.{format}` symlink to the newest image. Defaults to `true`.

```yaml
outputs:
  - type: file
    output_path: "/var/www/html/dashboard"
    render_interval: 60
    image_format: png
    keep_images: 1440
```

##### post

Pushes the rendered image via HTTP POST to a remote endpoint. Works with any device or service that accepts image uploads: networked displays, smart signage, ingestion APIs, and so on.

*   `url`: The endpoint to POST to.
*   `image_format` _(optional)_: `png`, `jpg`, `jpeg`, or `bmp`. Defaults to `"png"`.
*   `trigger` _(optional)_: When to push. `"on_dirty"` only pushes when content has changed. `"interval"` pushes on a fixed schedule regardless. Defaults to `"on_dirty"`.
*   `min_interval` _(optional)_: Minimum seconds between pushes. Defaults to `60`.
*   `auth` _(optional)_: Authentication. Supports `bearer` token or `basic` username/password.
*   `multipart` _(optional)_: Send the image as a `multipart/form-data` upload instead of raw bytes. Required for endpoints that expect a browser-style file upload.
    *   `field_name` _(optional)_: The form field name. Defaults to `"file"`.
    *   `filename` _(optional)_: The filename reported in the upload. Defaults to `image.<format>` (e.g. `image.jpeg`).
*   `after_post` _(optional)_: An additional HTTP request to fire after a successful upload. Useful for devices that require a separate "apply" or "display" call once the upload is complete.
    *   `url`: The URL to request.
    *   `method` _(optional)_: HTTP method. Defaults to `"GET"`.

By default the image is sent as raw bytes with the matching `Content-Type` header (`image/png`, `image/jpeg`, and so on).

```yaml
outputs:
  - type: post
    url: https://display.local/image
    image_format: jpeg
    trigger: on_dirty
    min_interval: 300
    auth:
      bearer: !secret display_token
```

For devices that use a multipart file upload and require a separate call to display the image:

```yaml
outputs:
  - type: post
    url: http://display.local/doUpload?dir=/image/
    image_format: jpeg
    trigger: on_dirty
    min_interval: 60
    multipart:
      field_name: file
    after_post:
      url: http://display.local/set?img=/image/image.jpeg
```

##### stream

Streams the latest frame to [remote displays](#remote-displays) over the
[HTTP server](#server) with real time updates using grydget's own protocol. Adding this output starts the server, and frames are served from the same port as `/notify` and `/theme`.

Grydgets ships with `grydgets-client`, a built-in client for this. See [Remote displays](#remote-displays)

*   `image_format` _(optional)_: `jpeg`, `jpg`, `png`, or `bmp`. Defaults to
    `"jpeg"`. The JPEG quality can't be configured.
*   `debounce_ms` _(optional)_: How long the dashboard has to stay still, in
    milliseconds, before a new frame is published. Defaults to `200`.

```yaml
outputs:
  - type: stream
    image_format: jpeg
    debounce_ms: 200
```

Clients subscribe to server sent events, and when something on the dashboard changes a new frame is sent, but only after it stays still for `debounce_ms`. This means that remote
displays don't show animations: they only update once things have stopped
moving. It's a little odd, but in practice I always turn off transitions in my dashboards.

The HTTP API used by the client is described under
[Writing your own client](#writing-your-own-client) in case you want to reimplement it, but in most cases you'll just want to use the built-in `grydgets-client`.

##### Combining outputs

You can use more than one output at the same time. For example, you can display the dashboard on screen while also pushing it to a remote display:

```yaml
outputs:
  - type: window
    fullscreen: true
  - type: post
    url: https://display.local/image
    image_format: jpeg
    trigger: on_dirty
    min_interval: 300
```

Or you can save it to disk and push it to a remote endpoint, without any display at all:

```yaml
outputs:
  - type: file
    output_path: "./snapshots"
    render_interval: 300
  - type: post
    url: https://dashboard-api.example.com/ingest
    trigger: interval
    min_interval: 60
```

##### Legacy configuration

For backwards compatibility, Grydgets still accepts the old `graphics` display settings and `headless` key. These are automatically translated to the new output system:

*   `headless.enabled: true` becomes a `file` output
*   `graphics.fb-device` becomes a `framebuffer` output
*   Otherwise, a `window` output is created from `graphics.fullscreen`

If you add an `outputs` key, the legacy display settings (`fullscreen`, `fb-device`, `x-display`) and `headless` block are ignored.

> ⚠️ Switching between display and non-display modes requires a restart. If you hot reload (`SIGUSR1`) a change to the display mode, Grydgets will warn you and skip it.

#### `server`

The `server:` block configures the HTTP server, which is used by some of the features. Note that having this section in the config doesn't start it on its
own. The server is only started if at least one of these features is in use:

| Feature | Endpoint it needs |
|---|---|
| A [notifiable widget](#notifiabletext) in `widgets.yaml` | `/notify` |
| A [`stream` output](#stream) | `/frame`, `/events` |
| [`appearance.http_control: true`](#appearance-day-and-night-themes) | `/theme` |

If none of the three features above are in use, Grydgets doesn't open
any ports and the `server:` block is ignored.

*   `host` _(optional)_: The address to bind to. Defaults to `127.0.0.1`, which
    is only reachable from the machine running Grydgets. Set it to `0.0.0.0` or
    to a LAN address if the server needs to be called from another machine, for
    example by a [remote display](#remote-displays) fetching frames or by Home
    Assistant posting a notification. Grydgets logs the address it's bound to at
    startup, and warns you if it's bound to loopback while a stream output or a
    notifiable widget is configured.
*   `port` _(optional)_: Defaults to `5000`.
*   `auth` _(optional)_: Bearer tokens for the two groups of endpoints.
    `stream_token` protects `/frame` and `/events`, and `control_token` protects
    `/notify` and `/theme`. You can set either one, both, or neither. An endpoint
    whose token isn't set can be called without one.

```yaml
server:
  host: 0.0.0.0
  port: 5000
  auth:
    stream_token: !secret stream_token
```

If configured, send the token in an `Authorization: Bearer <token>` header. A missing required token gets a `401`.

> ⚠️ If `control_token` isn't set, anyone who can reach the port can call
> `/notify`. That endpoint fetches an image from whatever URL is in the request
> body, so they can make your dashboard display anything they like.

If you [hot reload](#hot-reload) a configuration change that removes a feature
that uses an endpoint, that endpoint will stop being available and will return
a `404`. Starting or stopping the server itself requires a restart though, and Grydgets
will warn you if a reload would have changed that.

#### `appearance`: day and night themes

The `appearance:` block in `conf.yaml` names two [theme files](#theme-files)
and a location.
The dashboard switches from one theme to the other at that location's sunrise
and sunset. If you leave the block out, the same theme is used all day.

```yaml
appearance:
  latitude: 45.12
  longitude: -75.34
  themes:
    day: themes/day.yaml
    night: themes/night.yaml
  offsets:
    sunrise: 0
    sunset: -30
```

*   `themes.day`, `themes.night`: Theme files, resolved from `--config-dir` like every other path. Both are loaded and checked at startup, so even if you have an error in the night theme you'll see it right away if you start the dashboard during the day.
*   `latitude`, `longitude` _(optional, but both or neither)_: Decimal degrees, north and east positive. Sunrise and sunset are calculated locally, so the dashboard switches on time even without a network connection. Leave them out if you only want to switch themes over [HTTP](#setting-the-theme-over-http).
*   `offsets` _(optional)_: Minutes to move each boundary by, negative for earlier. Defaults to `0`.
*   `default` _(optional)_: The theme to use at startup, `day` or `night`. It's also the theme used on days when the sun doesn't rise or set (e.g. if you're close to the poles). Defaults to `day`.
*   `http_control` _(optional)_: Enables the [`/theme` endpoint](#setting-the-theme-over-http), which means the HTTP server gets started. Defaults to `false`.

If you don't provide coordinates, the [`/theme` endpoint](#setting-the-theme-over-http)
becomes the only way to change the theme. This is useful when you want
something else to decide, like a Home Assistant automation that watches a light
sensor or checks whether anybody is home. You'll need to set
`http_control: true` for this to work, otherwise there is no way to switch the
theme at all, and Grydgets will warn you about it at startup:

```yaml
appearance:
  default: night
  http_control: true
  themes:
    day: themes/day.yaml
    night: themes/night.yaml
```

> *N.B.* The coordinates don't need to be precise: being off by a degree moves
> sunset by about four minutes.

At startup and at every switch, Grydgets logs what it thinks the sun is doing.
This is the quickest way to check that the coordinates are right:

```
Sun at 45.12,-75.34: day from 05:57 to 19:45 local (offsets +0/-30 min); night theme at 19:45
```

You can also force a specific theme, or go back to following the sun, through
the [HTTP server](#setting-the-theme-over-http). That's the easiest way to check what both
themes look like without waiting for dusk.

### Dashboard layout options (`widgets.yaml`)

The widget tree is what makes up your dashboard. It lives in a file called `widgets.yaml`. A sample file is included in the
repository.

Every widget is a mapping with a `widget` key that names its type, followed by the parameters for that type. Container
widgets take a `children` list, which is how the tree is built. The root is usually a [`grid`](#grid):

```yaml
background_color: '#1b1b1b'
widgets:
  - widget: grid
    rows: 2
    columns: 2
    padding: 10
    children:
      - widget: text
        text: 'Top left'
      - widget: text
        text: 'Top right'
      - widget: text
        text: 'Bottom left'
      - widget: text
        text: 'Bottom right'
```

Every available widget type and its parameters is described under [Widgets](#widgets).

The top level of the file configures the screen itself, which is an implicit container for the whole dashboard:

*   `background_image` _(optional)_: The path to an image file to use as the background for the entire screen. Takes precedence over `background_color`. Can be a theme token, see [Theming](#theming).
*   `background_color` _(optional)_: A color for the screen background, see [Colors](#colors). Used when there is no `background_image`. Defaults to `[0, 0, 0]` (black).
*   `drop_shadow` _(optional)_: If `true`, a drop shadow effect will be applied to the main content of the screen. Defaults to `false`.
*   `widgets`: A list containing the root widget of your dashboard, see [Widgets](#widgets). Note that the screen currently only supports a single child widget.
*   `theme` _(optional)_: Named values and per-widget defaults, see [Theming](#theming).

### Secrets (`secrets.yaml`)

Sensitive values like tokens and passwords can be stored in a `secrets.yaml` file and referenced with the `!secret` tag:

```yaml
# secrets.yaml
hass_token: "your_secret_token_here"
api_key: "your_api_key"

# conf.yaml or widgets.yaml
auth:
  bearer: !secret hass_token
```

Keep `secrets.yaml` out of version control.

### Data Providers (`providers.yaml`)

Providers fetch data in the background and make it available to any number of widgets, so you don't have to call the same API once per widget. For example, if you have a widget for each day of the week's forecast, a single provider can fetch the whole forecast once and share it with all seven of them.

Providers are configured in `providers.yaml`:

```yaml
providers:
  hass_calendar:
    type: rest
    url: !secret hass_calendar_url
    headers:
      Authorization: !secret hass_bearer_token
    json_path: "events"  # Extract this from response
    jq_expression: 'map(select(.status == "active"))'  # Further filter with jq
    update_interval: 60  # Fetch every 60 seconds
    jitter: 5  # Add random 0-5 second delay

  weather_api:
    type: rest
    url: https://api.weather.com/current
    method: GET
    auth:
      bearer: !secret weather_token
    update_interval: 300
```

#### Provider Configuration Options

*   `type`: Provider type. Currently only `rest` is supported.
*   `url`: The URL to fetch from (required).
*   `method` _(optional)_: HTTP method (`GET`, `POST`, `PUT`, `DELETE`). Defaults to `GET`.
*   `headers` _(optional)_: Dictionary of HTTP headers.
*   `params` _(optional)_: Dictionary of query parameters.
*   `body` or `payload` _(optional)_: Request body for POST/PUT requests.
*   `auth` _(optional)_: Authentication options (see [Authentication Schemes](#authentication-schemes)).
*   `json_path` _(optional)_: Simple JSON path to extract from response (e.g., `"events[0].title"`).
*   `jq_expression` _(optional)_: jq expression for complex data transformations (e.g., `'.events[] | select(.active)'`).
*   `update_interval` _(optional)_: Seconds between fetches. Defaults to `60`.
*   `jitter` _(optional)_: A random delay between 0 and this many seconds added to each fetch, so that providers with the same interval don't all fire at the same time. Defaults to `0`.

If you specify both `json_path` and `jq_expression`, `json_path` is applied first and `jq_expression` runs on the result. This lets you narrow the data down before doing anything complicated with it.

## Widgets

Grydgets, as the name suggests, draws dashboards based on a series of _widgets_. Widgets are generally of two types:
Normal and Container.

**Normal widgets** draw something specific on the screen: a clock, the result of a REST call, an image, etc.

**Container widgets** determine where and how other widgets appear. A Grid widget, for example, lays other widgets out
in a grid. They can also change the appearance of what's inside them, e.g. by adding a label above or below another widget.

### General Widget Parameters

Most widgets support the following optional parameters:

*   `name` _(optional)_: A unique name for the widget instance. This is used for logging and for identifying notification widgets so you can send notifications to them. If not provided, the widget type name is used.

### Colors

Every color parameter accepts one of two forms, and you can use either one
anywhere, including for the top-level `background_color` and for nested chart
parameters like `bar_colors` and `bar_color_thresholds`.

**A list of RGB or RGBA components**, each `0`-`255`:

```yaml
color: [255, 136, 0]
color: [255, 136, 0, 204]   # with alpha
```

**A CSS-style string**:

| Form | Example | Meaning |
|---|---|---|
| `#rrggbb` | `'#ff8800'` | opaque |
| `#rrggbbaa` | `'#ff8800cc'` | with alpha |
| `#rgb` | `'#f80'` | shorthand for `#ff8800` |
| `#rgba` | `'#f80c'` | shorthand for `#ff8800cc` |
| color name | `'orange'` | any [CSS color name](https://www.w3.org/TR/css-color-3/#svg-color) |

Make sure to quote hex strings, since an unquoted `#` starts a YAML comment. A
color parameter also accepts a theme token (`color: !color accent`), see
[Theming](#theming).

```yaml
  - widget: dateclock
    time_color: '#eceff4'
    date_color: '#8fbcbb'
    background_color: '#000000a0'
```

If a color can't be parsed, Grydgets fails at load time with an error that
names the parameter. The one exception is a color sent to a `notifiabletext`
widget over the [HTTP server](#server): since that
comes from an outside caller while the dashboard is running, a bad value is
logged and ignored instead.

#### Naming

Similar to CSS, these parameter names mean the same thing on every widget:

*   `color`: the color of the widget's own content, whether that's text, a bar, or the fill of an `empty`.
*   `background_color`: the color painted behind that content.

Anything more specific is prefixed with what it applies to (`time_color`,
`pill_background_color`, `widget_background_color`).

### Authentication Schemes

Widgets that make HTTP requests (e.g., `rest`, `restimage`, `httpflip`) support an `auth` parameter. This is a dictionary specifying the authentication method:

*   `bearer`: A string representing a Bearer token.
*   `basic`: An object containing `username` and `password` strings for Basic authentication.

Example `auth` configuration:

```yaml
auth:
  bearer: !secret my_bearer_token
# OR
auth:
  basic:
    username: myuser
    password: mypassword
```

### Data extraction: `json_path` and `jq_expression`

For widgets and providers that read remote data, there are two ways to extract data from a JSON response:

**json_path**: simple path notation for basic extraction.
```yaml
json_path: "events[0].title"  # Get title of first event
json_path: "user.address.city"  # Navigate nested objects
```

**jq_expression**: a [jq](https://jqlang.github.io/jq/) expression, for anything more involved.
```yaml
jq_expression: '.events[] | select(.priority == "high")'  # Filter
jq_expression: '.items | map(.name) | join(", ")'  # Transform
jq_expression: '.[0].date | strptime("%Y-%m-%d") | strftime("%B %d")'  # Format
```

**Combining both**: `json_path` is applied first, then jq runs on the result.
```yaml
json_path: "events"  # Extract events array first
jq_expression: 'map(select(.active)) | .[0].title'  # Filter and extract
```

This works in:
- REST widgets (`rest`, `restimage`, `httpflip`)
- Data providers (`providers.yaml`)
- Provider widgets (`provider`, `providerflip`, `providerimage`)

### Container widgets

All Container widgets take a `children` parameter, specifying the list of widgets they're going to contain.

#### grid

A widget that places other widgets in a grid layout.

It supports the following parameters:

*   `rows`: The number of rows in the grid.
*   `columns`: The number of columns in the grid.
*   `padding` _(optional)_: The amount of padding around each child widget, in pixels. Defaults to `0`.
*   `background_color` _(optional)_: A background color for the grid itself (the "empty" space between widgets or behind the entire grid), see [Colors](#colors).
*   `widget_background_color` _(optional)_: A background color for each *child widget's cell*, see [Colors](#colors).
*   `widget_background_colors` _(optional)_: Per-cell background colors, overriding `widget_background_color` for the cells they name. See [Per-cell overrides](#per-cell-overrides).
*   `corner_radius` _(optional)_: The corner radius for the overall grid background, in pixels. Defaults to `0`.
*   `widget_corner_radius` _(optional)_: The corner radius for each child widget's background, in pixels. Defaults to `0`.
*   `widget_corner_radii` _(optional)_: Per-cell corner radii, overriding `widget_corner_radius` for the cells they name. See [Per-cell overrides](#per-cell-overrides).
*   `image_path` _(optional)_: The path to an image file to use as the background for the entire grid.
*   `drop_shadow` _(optional)_: If `true`, a drop shadow effect will be applied to the child widgets within the grid. Defaults to `false`.
*   `row_ratios` _(optional)_: A list representing the relative ratio of each row's height. E.g., `[1, 2]` means the second row will be twice as tall as the first. If not provided, rows have equal height.
*   `column_ratios` _(optional)_: A list representing the relative ratio of each column's width. E.g., `[1, 2]` means the second column will be twice as wide as the first. If not provided, columns have equal width.

Example:

```yaml
  - widget: grid
    rows: 2
    columns: 2
    padding: 4
    background_color: [50, 50, 50]
    widget_background_color: [70, 70, 70, 180]
    corner_radius: 10
    widget_corner_radius: 5
    row_ratios: [1, 2]
    column_ratios: [1, 2]
```

##### Per-cell overrides

`widget_background_colors` and `widget_corner_radii` take either a mapping keyed
on the `name` of a child, or a list with one entry per child. Cells that aren't
mentioned keep the grid-wide `widget_background_color` or
`widget_corner_radius`.

```yaml
  - widget: grid
    rows: 1
    columns: 3
    widget_background_color: "#2e3440"   # the default for every cell
    widget_background_colors:
      alert-tile: "#bf616a"              # ...except this one
    children:
      - widget: text
        name: alert-tile
        text: 'Alert'
      - widget: text
        text: 'Normal'
      - widget: text
        text: 'Normal'
```

In the list form, `null` means "don't override this one":

```yaml
    widget_background_colors: ["#bf616a", null, "#a3be8c"]
```

#### label

A widget that adds a text label above or below another widget. It can only have one child.

It supports the following parameters:

*   `text`: The text to display as the label.
*   `font_path` _(optional)_: The path to a ttf file to use as font for the label text.
*   `position` _(optional)_: `above` or `below` the child widget. Defaults to `above`.
*   `text_size` _(optional)_: The size of the label text in pixels.
*   `color` _(optional)_: The color of the label text, see [Colors](#colors). Defaults to `[255, 255, 255]` (white). This used to be called `text_color`.

Example:

```yaml
  - widget: label
    text: 'Random person'
    position: below
    text_size: 30
    color: [255, 255, 0]
    children:
      - widget: rest # ... some child widget
```

#### flip

A widget that cycles through its children, switching from one to the next at a fixed interval with an animated
transition.

It supports the following parameters:

*   `interval` _(optional)_: How long to wait before switching to the following widget, in seconds. Defaults to `5` seconds.
*   `transition` _(optional)_: How long the animation for transitioning to the following widget should last, in seconds. Defaults to `1` second. Set it to 0 to disable the animation altogether.
*   `ease` _(optional)_: Determines the ease factor of the transition animation. Higher values make the transition more abrupt at the beginning/end. Defaults to `2`.

Example:

```yaml
  - widget: flip
    interval: 5
    transition: 1
    ease: 3
    children:
      - widget: text # first child
      - widget: restimage # second child
```

#### httpflip

A `flip` widget that picks which child to display based on the response to an HTTP request.

It supports the following parameters:

*   `url`: The URL to retrieve the value from.
*   `mapping`: A dictionary where keys are expected response values (or extracted JSON paths) and values are the `name` of the child widget to display.
*   `default_widget`: The `name` of the child widget to display if the response value does not match any entry in `mapping`.
*   `json_path` _(optional)_: The path to the json item to extract from the HTTP response. If not provided, the raw response text is used.
*   `jq_expression` _(optional)_: jq expression to extract the comparison value from the JSON response. If both `json_path` and `jq_expression` are provided, `json_path` is applied first.
*   `auth` _(optional)_: Authentication options (see [Authentication Schemes](#authentication-schemes)).
*   `method` _(optional)_: The HTTP method to use (`GET` or `POST`). Defaults to `GET`.
*   `payload` _(optional)_: A dictionary representing the JSON payload for `POST` requests.
*   `update_frequency` _(optional)_: How often the HTTP request should be made, in seconds. Defaults to `30` seconds.
*   `static` _(optional)_: If `true`, the HTTP request is only made once at startup and never repeated. Useful when you know the value is never going to change. Defaults to `false`.

**Inherited from `flip` widget:**
*   `interval` _(optional)_: How long to wait before checking for changes, in seconds. Defaults to `5` seconds.
*   `transition` _(optional)_: How long the animation for transitioning should last, in seconds. Defaults to `1` second. Set it to 0 to disable the animation altogether.
*   `ease` _(optional)_: Determines the ease factor of the transition animation. Higher values make the transition more abrupt at the beginning/end. Defaults to `2`.

Example:

```yaml
  - widget: httpflip
    default_widget: motioneye-cam
    update_frequency: 60
    url: "https://homeassistant.example.com/api/template"
    method: POST
    auth:
      bearer: !secret hass_token
    payload:
      template: '{{ (now() > today_at("18:00")) and (now() - states.switch.sonoff_meter_plug_4_relay.last_changed).seconds < (60*60*2) }}'
    mapping:
      "False": main-cam
      "True": other-cam
    children:
      - widget: restimage
        name: main-cam
        url: http://192.168.255.34/image.jpg
      - widget: restimage
        name: other-cam
        url: 'https://motioneye.example.com/picture/13/current'
```

#### scheduleflip

A `flip` widget that picks which child to display based on the time of day. It accepts all the parameters of `flip`.

It supports the following parameters:

*   `schedule`: A dictionary mapping time strings (`HH:MM` format) to the `name` of the child widget to display at or after that time, until the next scheduled time.
*   `interval` _(optional)_: How long to wait before checking the schedule again, in seconds. Defaults to `5` seconds.
*   `transition` _(optional)_: How long the animation for transitioning to the following widget should last, in seconds. Defaults to `1` second. Set it to 0 to disable the animation altogether.
*   `ease` _(optional)_: Determines the ease factor of the transition animation. Defaults to `2`.

Example:

```yaml
  - widget: scheduleflip
    schedule:
      "08:00": morning-widget
      "18:00": evening-widget
    children:
      - widget: text
        name: morning-widget
        text: "Good Morning!"
      - widget: text
        name: evening-widget
        text: "Good Evening!"
```

#### pill

A container widget that draws a pill-shaped overlay on top of another widget. Useful for adding a badge or a status indicator to an image.

It supports the following parameters:

*   `circular_mask` _(optional)_: If `true`, applies a circular mask to the base (first) widget. Defaults to `false`.
*   `widget_background_color` _(optional)_: Background color for the masked widget when using circular mask. See [Colors](#colors).
*   `pill_background_color` _(optional)_: Background color for the pill overlay. See [Colors](#colors). Defaults to transparent.
*   `pill_width_percent` _(optional)_: Width of the pill as a percentage of container width (0.0-1.0). Defaults to `0.8`.
*   `pill_height_percent` _(optional)_: Height of the pill as a percentage of container height (0.0-1.0). Defaults to `0.2`.
*   `pill_position_x` _(optional)_: Horizontal center position of the pill (0.0-1.0). Defaults to `0.5` (centered).
*   `pill_position_y` _(optional)_: Vertical center position of the pill (0.0-1.0). Defaults to `0.8` (lower area).
*   `pill_corner_radius` _(optional)_: Corner radius for the pill shape in pixels. If not specified, the pill is fully rounded (semicircular ends).
*   `pill_size_relative_to_circle` _(optional)_: If `true` and `circular_mask` is enabled, the pill size is relative to the circle diameter. This is useful if you have a rectangular slot with a centered profile picture and want to make the pill the same width as the round picture. Defaults to `false`.
*   `children`: Exactly 2 child widgets. First is the base widget, second is the overlay widget.

Example:

```yaml
  - widget: pill
    circular_mask: true
    widget_background_color: [40, 0, 40, 150]
    pill_background_color: [0, 0, 0, 150]
    pill_width_percent: 1.4
    pill_height_percent: 0.25
    pill_position_y: 0.85
    pill_size_relative_to_circle: true
    children:
      - widget: restimage
        url: "file://images/profile.png"
        preserve_aspect_ratio: true
      - widget: text
        text: "Online"
        font_path: 'OpenSans-Regular.ttf'
        color: [0, 255, 0]
        align: center
```

#### notifiabletext

A container widget that can display a temporary text notification over its main child widget. It can only have one child.

It supports the following parameters:

*   `font_path`: The path to a ttf file to use as font for the notification text.
*   `padding` _(optional)_: The amount of padding around the notification text in pixels. Defaults to `0`.
*   `text_size` _(optional)_: The size of the notification text in pixels.
*   `color` _(optional)_: The default color of the notification text, see [Colors](#colors). Defaults to `[255, 255, 255]` (white).
*   `background_color` _(optional)_: The default background color behind the notification, see [Colors](#colors). Unset by default, so the notification text appears over whatever is behind it.
*   `corner_radius` _(optional)_: The corner radius for `background_color`, in pixels. Defaults to `0`.

To send a notification, POST to `/notify` on the
[HTTP server](#server). The server binds to `127.0.0.1` by
default, so you'll need to set `server.host` if the request is coming from
another machine, and if `control_token` is set you'll need to send it in an
`Authorization: Bearer <token>` header.

The POST body takes `widget`, `text`, and optionally `duration`, `color`, and
`background_color`. If you pass `color` or `background_color`, they override
the widget's configured values for that one notification only, so the next
notification goes back to the configured look. A colour that can't be parsed
is logged and ignored.

Example:

```yaml
  - widget: notifiabletext
    name: fullscreen-notification
    font_path: 'OpenSans-ExtraBold.ttf'
    padding: 10
    text_size: 100
    children:
      - widget: grid # ... main content widget
```

```bash
curl -X POST \
     -H "Content-Type: application/json" \
     -d '{"widget": "fullscreen-notification", "text": "This is a test notification from curl!", "duration": 10}' \
     http://192.168.1.1:5000/notify
```

An alert with its own colours:

```bash
curl -X POST \
     -H "Content-Type: application/json" \
     -d '{"widget": "fullscreen-notification", "text": "Somebody is at the door!", "color": "#ffffff", "background_color": "#bf616a", "duration": 15}' \
     http://192.168.1.1:5000/notify
```

#### notifiableimage

A container widget that can display a temporary image notification over its main child widget. It can only have one child.

It has no parameters other than the common `name`.

To send a notification, POST to `/notify` on the [HTTP server](#server) with the `url` of the image and an optional `duration` in seconds. The same notes about `server.host` and `control_token` as for [`notifiabletext`](#notifiabletext) apply.

Example:

```yaml
  - widget: notifiableimage
    name: fullscreen-notification-image
    children:
      - widget: notifiabletext # ... main content widget (which itself could be notifiable)
```

```bash
curl -X POST \
     -H "Content-Type: application/json" \
     -d '{"widget": "fullscreen-notification-image", "url": "https://example.com/your_image.jpg"}' \
     http://192.168.1.1:5000/notify
```

### Normal widgets

#### text

A simple widget that displays some text.

It supports the following parameters:

*   `text` _(optional)_: The text to display. Defaults to an empty string `''`.
*   `text_size` _(optional)_: The size of the text in pixels. If not provided, it automatically adjusts to fit the widget's height.
*   `font_path` _(optional)_: The path to a ttf file to use as font. If not provided, Pygame's default font is used.
*   `color` _(optional)_: The color of the text, see [Colors](#colors). Defaults to `[255, 255, 255]` (white).
*   `background_color` _(optional)_: A background color painted behind the text, see [Colors](#colors). Covers the whole widget: `padding` insets the text and leaves the backdrop alone. Unset by default, leaving the widget transparent.
*   `corner_radius` _(optional)_: The corner radius for `background_color`, in pixels. Defaults to `0`.
*   `padding` _(optional)_: The amount of padding around the text in pixels. Defaults to `0`.
*   `align` _(optional)_: The horizontal alignment for the text. One of `left`, `center`, or `right`. Defaults to `left`.
*   `vertical_align` _(optional)_: The vertical alignment for the text. One of `top`, `center`, or `bottom`. Defaults to `top`.

Example:

```yaml
  - widget: text
    text: 'Hello Grydgets!'
    text_size: 50
    font_path: 'OpenSans-Regular.ttf'
    color: [0, 255, 0]
    background_color: "#2e3440"
    corner_radius: 12
    align: center
    vertical_align: center
```

Giving a text widget its own `background_color` saves you from wrapping it in a
`grid` just to get a `widget_background_color`.

#### dateclock

A widget that displays a 24-hour clock at the top, and the current date at the bottom.

It supports the following parameters:

*   `time_font_path`: The path to a ttf file to use as font for the time.
*   `date_font_path`: The path to a ttf file to use as font for the date.
*   `color` _(optional)_: The color of the time and date text, see [Colors](#colors). Defaults to `[255, 255, 255]` (white).
*   `time_color` _(optional)_: The color of the time only. Overrides `color` for the time line.
*   `date_color` _(optional)_: The color of the date only. Overrides `color` for the date line.
*   `background_color` _(optional)_: The background color for the clock widget, see [Colors](#colors).
*   `corner_radius` _(optional)_: The corner radius for the clock widget's background, in pixels. Defaults to `0`.

The time and the date are drawn as separate lines, and each can have its own
font and colour. This is useful if you want a fancy display font for the time
and a plainer one for the date.

Example:

```yaml
  - widget: dateclock
    time_font_path: 'fonts/Fraunces-700.ttf'
    date_font_path: 'fonts/Inter-400.ttf'
    time_color: [236, 239, 244]
    date_color: [143, 188, 187]
    background_color: [0, 0, 0, 160]
    corner_radius: 25
```

#### rest

A widget that makes periodic HTTP requests and displays the response text. It supports JSON extraction and custom formatting of the final text.

It supports the following parameters:

*   `url`: The URL to retrieve.
*   `json_path` _(optional)_: The path to the JSON item to extract from the HTTP response. Supports nested objects and array indexing (e.g., `address.city` or `items[0].name`).
*   `jq_expression` _(optional)_: jq expression for complex data transformations (e.g., `.items[] | select(.active)`). If both `json_path` and `jq_expression` are provided, `json_path` is applied first.
*   `format_string` _(optional)_: A Python format string to be used to format the final text. The extracted value is passed as the first argument. Defaults to `{}`.
*   `method` _(optional)_: The HTTP method to use (`GET` or `POST`). Defaults to `GET`.
*   `payload` _(optional)_: A dictionary representing the JSON payload for `POST` requests.
*   `auth` _(optional)_: Authentication options (see [Authentication Schemes](#authentication-schemes)).
*   `update_frequency` _(optional)_: How often the HTTP request should be made, in seconds. Defaults to `30` seconds.
*   `static` _(optional)_: If `true`, the HTTP request is made only once on startup and never repeated. Useful when displaying a fixed value. Defaults to `false`.
*   `font_path` _(optional)_: The path to a ttf file to use as font. If not provided, Pygame's default font is used.
*   `text_size` _(optional)_: The size of the text in pixels. If not provided, it automatically adjusts to fit the widget's height.
*   `color` _(optional)_: The color of the text, see [Colors](#colors). Defaults to `[255, 255, 255]` (white).
*   `background_color` _(optional)_: A background color painted behind the text, see [Colors](#colors). Covers the whole widget: `padding` insets the text and leaves the backdrop alone. Unset by default, leaving the widget transparent.
*   `corner_radius` _(optional)_: The corner radius for `background_color`, in pixels. Defaults to `0`.
*   `padding` _(optional)_: The amount of padding around the text in pixels. Defaults to `6`.
*   `align` _(optional)_: The horizontal alignment for the text. One of `left`, `center`, or `right`. Defaults to `center`.
*   `vertical_align` _(optional)_: The vertical alignment for the text. One of `top`, `center`, or `bottom`. Defaults to `center`.

Example:

```yaml
  - widget: rest
    url: 'https://jsonplaceholder.typicode.com/users/1'
    json_path: 'address.city'
    format_string: 'lives in {}'
    text_size: 70
    update_frequency: 60
    auth:
      bearer: !secret my_api_token
    method: GET
```

#### provider

A widget that displays data from a configured data provider. Unlike a `rest` widget, which makes its own HTTP request, a provider widget reads from a shared provider defined in `providers.yaml`, so several widgets can use the same data without each one fetching it separately.

Provider widgets update when the backing provider updates, even if the data didn't change.

It supports the following parameters:

*   `providers`: A list containing exactly one provider name (e.g., `[hass_calendar]`).
*   `data_path` _(optional)_: JSON path to extract from provider data.
*   `jq_expression` _(optional)_: jq expression to extract/transform provider data. If both are provided, `data_path` is applied first.
*   `format_string` _(optional)_: Python format string for display. The value is passed as `{value}`. Defaults to `"{value}"`.
*   `fallback_text` _(optional)_: Text to show on error or missing data. Defaults to `"--"`.
*   `show_errors` _(optional)_: If `true`, displays error messages instead of fallback text. Defaults to `false`.
*   `font_path` _(optional)_: Path to a ttf font file.
*   `text_size` _(optional)_: Text size in pixels.
*   `color` _(optional)_: The color of the text, see [Colors](#colors). Defaults to `[255, 255, 255]` (white).
*   `background_color` _(optional)_: A background color painted behind the text, see [Colors](#colors). Covers the whole widget: `padding` insets the text and leaves the backdrop alone. Unset by default, leaving the widget transparent.
*   `corner_radius` _(optional)_: The corner radius for `background_color`, in pixels. Defaults to `0`.
*   `padding` _(optional)_: The amount of padding around the text in pixels. Defaults to `6`.
*   `align` _(optional)_: The horizontal alignment for the text. One of `left`, `center`, or `right`. Defaults to `center`.
*   `vertical_align` _(optional)_: Vertical alignment (`top`, `center`, `bottom`). Defaults to `center`.

Example:

```yaml
providers:
  my_calendar:
    type: rest
    url: !secret calendar_api
    update_interval: 60

widgets:
  - widget: grid
    rows: 3
    children:
      - widget: provider
        providers: [my_calendar]
        data_path: "[0].title"
        fallback_text: "No events"
      - widget: provider
        providers: [my_calendar]
        data_path: "[0].location"
      - widget: provider
        providers: [my_calendar]
        jq_expression: '.[0].start | strptime("%Y-%m-%d") | strftime("%A")'
```

#### providertemplate

A widget that renders data from providers using Home Assistant's Jinja2 template engine. Useful for formatting that needs Home Assistant's own template functions and filters. I know, this one is a bit weird since it uses a specific service. It's my project! I can do what I want!

Provider widgets update when the backing provider updates, even if the data didn't change.

It supports the following parameters:

*   `providers`: A list of provider names (can be multiple, e.g., `[calendar, weather]`).
*   `template`: Jinja2 template string. Each provider's data is available as `provider_<name>` (e.g., `provider_calendar`, `provider_weather`).
*   `hass_url`: Home Assistant instance URL (required).
*   `hass_token`: Home Assistant authentication token (required).
*   `fallback_text` _(optional)_: Text to show on error. Defaults to `"--"`.
*   `font_path` _(optional)_: Path to a ttf font file.
*   `text_size` _(optional)_: Text size in pixels.
*   `color` _(optional)_: The color of the text, see [Colors](#colors). Defaults to `[255, 255, 255]` (white).
*   `background_color` _(optional)_: A background color painted behind the text, see [Colors](#colors). Covers the whole widget: `padding` insets the text and leaves the backdrop alone. Unset by default, leaving the widget transparent.
*   `corner_radius` _(optional)_: The corner radius for `background_color`, in pixels. Defaults to `0`.
*   `padding` _(optional)_: The amount of padding around the text in pixels. Defaults to `6`.
*   `align` _(optional)_: The horizontal alignment for the text. One of `left`, `center`, or `right`. Defaults to `center`.
*   `vertical_align` _(optional)_: Vertical alignment. Defaults to `center`.

Example:

```yaml
- widget: providertemplate
  providers: [hass_calendar, weather_api]
  hass_url: !secret hass_url
  hass_token: !secret hass_token
  template: |
    {% set event = provider_hass_calendar[0] %}
    {% set weather = provider_weather_api %}
    {{ event.title }} at {{ event.start_time | as_timestamp | timestamp_custom('%I:%M %p') }}
    Weather: {{ weather.temp }}°F
  fallback_text: "Loading..."
```

#### providerflip

A `flip` widget that picks which child to display based on data from a provider. It works like `httpflip`, but reads from a shared provider instead of making its own HTTP requests.

Provider widgets update when the backing provider updates, even if the data didn't change.

It supports the following parameters:

*   `providers`: A list containing exactly one provider name.
*   `data_path` _(optional)_: JSON path to extract the comparison value from provider data.
*   `jq_expression` _(optional)_: jq expression to extract the comparison value.
*   `mapping`: Dictionary mapping values to child widget names.
*   `default_widget`: Name of the child widget to display by default or when no mapping matches.
*   `interval` _(optional)_: How often to check the provider for data changes, in seconds. Defaults to `5` seconds.
*   `transition` _(optional)_: Transition animation duration in seconds. Defaults to `1`.
*   `ease` _(optional)_: Easing factor for transition. Defaults to `2`.

If the provider returns an error, the widget keeps displaying the current child.

Example:

```yaml
providers:
  camera_switch:
    type: rest
    url: https://homeassistant.example.com/api/template
    method: POST
    auth:
      bearer: !secret hass_token
    payload:
      template: '{{ is_state("switch.camera_mode", "on") }}'
    update_interval: 10

widgets:
  - widget: providerflip
    providers: [camera_switch]
    default_widget: cam_a
    transition: 0.5
    mapping:
      "True": cam_a
      "False": cam_b
    children:
      - widget: restimage
        name: cam_a
        url: http://192.168.1.10/image.jpg
      - widget: restimage
        name: cam_b
        url: http://192.168.1.11/image.jpg
```

#### providerimage

A widget that displays an image from a URL found in provider data. It works like `restimage`, but takes the image URL from a provider. Both HTTP(S) URLs and local `file://` paths are supported.

Provider widgets update when the backing provider updates, even if the data didn't change.

It supports the following parameters:

*   `providers`: A list containing exactly one provider name.
*   `data_path` _(optional)_: JSON path to extract the image URL from provider data.
*   `jq_expression` _(optional)_: jq expression to extract the image URL.
*   `fallback_image` _(optional)_: Path to a fallback image file to display on error.
*   `auth` _(optional)_: Authentication for fetching the image from HTTP/HTTPS URLs (not used for `file://` URLs).
*   `preserve_aspect_ratio` _(optional)_: If `true`, maintains the original image aspect ratio when scaling. If `false` (default), the image is stretched to fill the container.
*   `show_errors` _(optional)_: If `true`, displays error messages instead of a fallback image. Defaults to `false`.

The extracted URL can be:
- HTTP/HTTPS URL: `https://example.com/image.jpg`
- Local file path: `file:///path/to/image.jpg`

Example:

```yaml
providers:
  camera_urls:
    type: rest
    url: https://api.example.com/cameras
    json_path: "active_cameras"
    update_interval: 30

widgets:
  - widget: providerimage
    providers: [camera_urls]
    data_path: "[0].image_url"
    fallback_image: "camera_offline.png"

  # Example with file:// URLs
  - widget: providerimage
    providers: [local_images]
    data_path: "current_image"
    # Provider returns: {"current_image": "file:///home/user/images/photo.jpg"}
```

Since the `json_path` functionality is pretty powerful, you can do some clever stuff here like reference different local weather icon files based on the value of a weather provider. For example:

```yaml
  - widget: providerimage
    providers:
      - hourly_weather_api
    data_path: 'forecast[0].condition'
    jq_expression: '"file://images/weather/" + . + ".png"'
```


#### restimage

A widget that periodically fetches an image and displays it. It can also fetch a JSON document, extract an image URL from it, and then fetch that. Both HTTP(S) URLs and local `file://` paths are supported.

It supports the following parameters:

*   `url`: The URL to retrieve the image from (HTTP/HTTPS or `file://` URL).
*   `json_path` _(optional)_: The path to the JSON item that contains an image URL to retrieve. If specified, the value at this path will be used as the actual image URL.
*   `jq_expression` _(optional)_: jq expression to extract the image URL from the JSON response. If both `json_path` and `jq_expression` are provided, `json_path` is applied first.
*   `auth` _(optional)_: Authentication options for HTTP/HTTPS requests (see [Authentication Schemes](#authentication-schemes)). Not used for `file://` URLs.
*   `update_frequency` _(optional)_: How often the image should be refreshed, in seconds. Defaults to `30` seconds.
*   `static` _(optional)_: If `true`, the image is loaded only once on startup and never re-fetched. Useful for local files or remote images that never change. Defaults to `false`.
*   `preserve_aspect_ratio` _(optional)_: If `true`, maintains the original image aspect ratio when scaling. If `false` (default), the image is scaled to fill the container.

The URL (either directly specified or extracted via `json_path`/`jq_expression`) can be:
- HTTP/HTTPS URL: `https://example.com/image.jpg`
- Local file path: `file:///path/to/image.jpg`

Examples:

```yaml
  # HTTP image
  - widget: restimage
    url: 'https://motioneye.example.com/picture/9/current/'
    auth:
      basic:
        username: camera_user
        password: camera_password
    update_frequency: 10

  # Local file
  - widget: restimage
    url: 'file:///home/user/images/current.jpg'
    update_frequency: 5

  # Extract URL from JSON (can return either HTTP or file:// URL)
  - widget: restimage
    url: 'https://api.example.com/current-image'
    json_path: 'image_url'
    update_frequency: 10
```

Since the `json_path` functionality is pretty powerful, you can do some clever stuff here like reference different local weather icon files based on the value of a weather API. For example:

```yaml
  - widget: restimage
    url: 'https://weather.example.com/tokyo'
    data_path: 'forecast[0].condition'
    jq_expression: '"file://images/weather/" + . + ".png"'
```

#### empty

A widget that takes up space without drawing anything. Use it to leave a hole
in a grid, or give it a `color` to use it as a divider or as a plain coloured
block.

It supports the following parameters:

*   `color` _(optional)_: The color to fill the widget with, see [Colors](#colors). Unset by default, leaving the widget fully transparent.
*   `corner_radius` _(optional)_: The corner radius for `color`, in pixels. Defaults to `0`.

Example:

```yaml
  # A 2px rule between two rows
  - widget: empty
    color: [255, 255, 255, 40]
```

#### providerbarchart

A widget that renders a bar chart from a list of numeric values sourced from a data provider. It's deliberately minimal, with no axes or legend. I had to draw the line somewhere.

It supports the following parameters:

*   `providers`: A list containing exactly one provider name.
*   `data_path` _(optional)_: JSON path to extract the list of values from provider data.
*   `jq_expression` _(optional)_: jq expression that must return a JSON array of numbers.
*   `bar_color` _(optional)_: Default color of the bars, see [Colors](#colors). Defaults to `[100, 149, 237]` (cornflower blue).
*   `bar_colors` _(optional)_: A mapping of label strings to colors (see [Colors](#colors)). Bars whose label matches a key are drawn in the corresponding color, taking priority over `bar_color_thresholds` and `bar_color`.
*   `bar_color_thresholds` _(optional)_: A list of `{above: <value>, color: <color>}` entries (see [Colors](#colors)). Each bar is colored by the first threshold whose `above` value is less than or equal to the bar's value. Checked in descending order. Falls back to `bar_color` if no threshold matches.
*   `bar_background_colors` _(optional)_: A mapping of label strings to colors (see [Colors](#colors)). Draws a full-height background rectangle behind the matching bar. Useful for marking specific bars, since the background is visible even when the value is zero.
*   `bar_gap` _(optional)_: Gap between bars in pixels. Defaults to `2`.
*   `max_value` _(optional)_: Fixed maximum value for the chart. If not provided, auto-scales to the maximum value in the data.
*   `min_value` _(optional)_: Minimum value for the chart. Defaults to `0`.
*   `midline` _(optional)_: If `true`, draws a horizontal marker line at the 50% point behind the bars. Defaults to `false`.
*   `midline_thickness` _(optional)_: Thickness of the midline in pixels. Defaults to `1`.
*   `midline_color` _(optional)_: Color of the midline, see [Colors](#colors). Defaults to `[255, 255, 255]` (white).
*   `quartline` _(optional)_: If `true`, draws horizontal marker lines at the 25% and 75% points behind the bars. Defaults to `false`.
*   `quartline_thickness` _(optional)_: Thickness of the quartlines in pixels. Defaults to `1`.
*   `quartline_color` _(optional)_: Color of the quartlines, see [Colors](#colors). Defaults to `[255, 255, 255]` (white).
*   `labels_jq_expression` _(optional)_: jq expression that returns a JSON array of strings to use as bar labels.
*   `labels_data_path` _(optional)_: JSON path alternative to `labels_jq_expression`.
*   `label_font_path` _(optional)_: Path to a ttf font file for the labels.
*   `label_size` _(optional)_: Font size for the labels in pixels. Defaults to `12`.
*   `label_color` _(optional)_: Color of the label text, see [Colors](#colors). Defaults to `[200, 200, 200]`.

Example (hourly rain probability for the next 24 hours):

```yaml
providers:
  hourly_weather:
    type: rest
    url: https://weather.example.com/api/hourly
    update_interval: 3600

widgets:
  - widget: providerbarchart
    providers: [hourly_weather]
    jq_expression: "[.forecast[:24][].precipitation_probability]"
    labels_jq_expression: "[.forecast[:24][].datetime | .[11:13]]"  # extract the hour digits from the timestamp
    bar_color: [100, 149, 237]
    bar_color_thresholds:
      - above: 70
        color: [220, 80, 80]
      - above: 40
        color: [220, 160, 60]
    bar_background_colors:
      "00": [255, 255, 255, 25]
    bar_gap: 2
    max_value: 100
    midline: true
    midline_color: [255, 255, 255, 120]
    quartline: true
    quartline_color: [255, 255, 255, 60]
    label_font_path: OpenSans-Regular.ttf
    label_size: 20
```

## Theming

The `theme:` block in `widgets.yaml` lets you define colours, fonts and sizes
once and refer to them by name from the rest of the file. It also lets you set defaults per widget
type, so that most widgets don't need to specify them at all.

```yaml
theme:
  colors:
    panel: '#3b4252'
    text: '#eceff4'
    text-muted: '#a3afc2'
  fonts:
    regular: fonts/Inter-400.ttf
    bold: fonts/Inter-800.ttf
  sizes:
    radius: 25

  groups:
    text-like: [text, rest, provider, providertemplate, notifiabletext, label]
  defaults:
    text-like:
      font_path: !font regular
      color: !color text
    grid:
      widget_background_color: !color panel
      widget_corner_radius: !size radius

widgets:
  - widget: grid
    children:
      - widget: text
        text: Kitchen              # font_path and color come from the theme
      - widget: text
        text: 21.4°
        color: !color text-muted   # a widget's own value always wins
```

### Tokens

There's a bit of magic here. Every key under `theme` other than `groups` and `defaults` is a **token
section**, and the name of the section is also the YAML tag used to read from
it: `!color panel` refers to `theme.colors.panel`, and `!font regular` to
`theme.fonts.regular`. You can name sections whatever you like: if you add a
`spacings:` section, `!spacing tight` will work. A tag matches a section with
the same name, with or without a trailing `s`.

A token can be used anywhere a literal value can, including inside mappings and
lists such as a grid's per-cell overrides:

```yaml
  - widget: grid
    widget_background_colors:
      alert-cell: !color danger
```

A theme entry can itself be a token (`panel-raised: !color panel`). If you
refer to a name that isn't defined, Grydgets fails at load time with an error
that names the section and lists the entries it does contain. A loop between
entries is also an error.

The screen's own top-level keys accept tokens too, which is how a theme can
change the background of the whole dashboard. `theme.defaults` can't be applied
to them, since the screen isn't a widget under `widgets:`, so you have to write
the tokens on them yourself:

```yaml
theme:
  colors:
    screen: '#1b1b1b'
  images:
    screen: images/background.jpg

background_image: !image screen
background_color: !color screen
```

If a theme wants a flat colour instead of a wallpaper, it can set
`images.screen` to `null`: the screen falls back to `background_color` whenever
there's no image. Since a [theme file](#theme-files) has to define everything
the base theme does, every theme has to say which of the two it wants, so
there's no way for a theme to accidentally inherit the wrong wallpaper by
leaving the entry out.

```yaml
# themes/flat.yaml
colors:
  screen: '#f5f5f5'
images:
  screen: null
```

### Defaults

`theme.defaults` is keyed by widget type. Every widget of that type that doesn't
set a parameter itself gets the value from the theme:

```yaml
  defaults:
    grid:
      widget_corner_radius: 25
```

However, many widget types draw text even though they aren't `text` widgets (`rest`,
`provider`, and so on). `theme.groups` lets you give a name to a set of widget
types, so that you can apply the same defaults to all of them at once:

```yaml
  groups:
    text-like: [text, rest, provider, providertemplate, notifiabletext, label]
  defaults:
    text-like:
      font_path: !font regular
```

A default set on a specific widget type always wins over one set on a group
that the type belongs to, regardless of the order they're written in. Note that
`dateclock` (`time_font_path`, `date_font_path`) and `providerbarchart`
(`label_font_path`, `label_color`) use their own parameter names, so they need
their own entries.

Keep in mind that if you don't want a specific widget to pick up a default, you have to override it explicitly (for example with `widget_corner_radius: 0`).

Tokens only work in the widgets file. Using one in `conf.yaml` or
`providers.yaml` is an error.

### Theme files

The `theme:` block in the widgets file is the base theme, and it's what gets
used unless you say otherwise. Passing `--theme FILE` replaces it with a
different one, so you can render the same widget tree with a different look
without editing it:

```bash
grydgets --theme themes/light.yaml
```

A theme file contains the same things you'd write under `theme:` (the token
sections, `groups` and `defaults`), but at the top level of the file, without
the `theme:` key:

```yaml
# themes/light.yaml
colors:
  text: '#2e3440'
  panel: '#d8dee9'
fonts:
  regular: fonts/Inter-400.ttf
  bold: fonts/Inter-800.ttf
sizes:
  radius: 25

groups:
  text-like: [text, rest, provider, providertemplate, notifiabletext, label]
defaults:
  text-like:
    font_path: !font regular
    color: !color text
  grid:
    widget_corner_radius: !size radius
```

The theme file replaces the base theme completely: nothing from the base theme
is merged in, and tokens used in the theme file's `defaults` are resolved
against the theme file itself. This means that a theme file has to define
**everything** the base theme does, `groups` and `defaults` included. If you
loaded a file that only listed colours, the defaults would disappear and the
text widgets would be left without a font, so Grydgets checks the file when
it's loaded and fails with an error that lists the missing entries. Defining
*more* than the base theme is fine.

Relative paths inside a theme file are resolved from `--config-dir`, like
everywhere else. The file is read again on [hot reload](#hot-reload), so you
can edit a theme and send `SIGUSR1` to see the result without restarting.

You can also configure two theme files in `conf.yaml` instead of one on the
command line, and have the dashboard switch between them at sunrise and sunset.
See [Day and night themes](#appearance-day-and-night-themes).

### Setting the theme over HTTP

If [`appearance.http_control`](#appearance-day-and-night-themes) is `true`, you can POST
to `/theme` on the [HTTP server](#server) to force a specific
theme regardless of the sun, or to hand control back to it. Without that
setting the endpoint returns `404`.

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"mode": "night"}' http://localhost:5000/theme
# {"success": true, "mode": "night", "following_sun": false,
#  "held_until": "2026-08-09T23:56:59+00:00"}
```

*   `mode`: `day`, `night`, or `auto` to follow the sun again from now.
*   `hold` _(optional)_: How long a `day` or `night` choice lasts. `next` (the default) holds it until the sun's next sunrise or sunset, and then goes back to following the sun. `forever` holds it until `auto` is sent or the dashboard restarts.

The default is `next` so that forcing the night theme once in the afternoon
doesn't leave the dashboard dark the next morning. If there are no coordinates
configured, there's no sunrise or sunset to wait for, so every choice holds
until the next one.

A `GET` on the same URL reports the state without changing it:

```bash
curl http://localhost:5000/theme
# {"success": true, "mode": "day", "following_sun": true, "held_until": null,
#  "next_change": "2026-08-09T23:56:59+00:00", "next_mode": "night"}
```

If there is only one theme, or if `--theme` was passed on the command line,
the endpoint returns a `400` saying so. The same happens if you send `auto`
without any coordinates configured. A `404` means `http_control` is off.

## Remote displays

You can render the dashboard on one machine and display it on another. The
rendering machine runs Grydgets with a [`stream` output](#stream), and each
screen runs `grydgets-client`, which connects to it, fetches a new frame
whenever one is published, and displays it. The remote screens don't build a widget
tree at all, don't run any providers, and don't need fonts, images, or a
`widgets.yaml`.

This is useful when the screen devices are too slow to render the dashboard
themselves. For example, drawing a hundred widgets on a 1080p surface takes long enough on a
Raspberry Pi that a notification can show up to 20 seconds late, while a desktop can
do it quickly and run at a higher `fps-limit`.

If a device can't run `grydgets-client`, like a photo frame or a signage box
that only accepts uploads, you can push frames to it with a
[`post` output](#pushing-frames-with-a-post-output) instead.

```
     rendering host                        screens
  ┌────────────────────┐             ┌──────────────────┐
  │ grydgets           │   /events   │ grydgets-client  │
  │  widgets.yaml      │ ──────────► │  client.yaml     │
  │  providers.yaml    │   /frame    │   window or      │
  │  outputs: [stream] │ ◄────────── │   framebuffer    │
  └────────────────────┘             └──────────────────┘
```

### On the rendering host

Add a `stream` output, bind the server to an address that the screens can
reach, and raise `fps-limit`. Notifications are only picked up when a frame is
rendered, so a low `fps-limit` can make them show up late.

```yaml
graphics:
  fps-limit: 10
  resolution: [1920, 1080]
server:
  host: 0.0.0.0
  port: 5000
  auth:
    stream_token: !secret stream_token
outputs:
  - type: stream
    image_format: jpeg
```

The rendering host doesn't need a screen of its own, since there is no display
output. A single process can serve every remote screen, each at the size it asks for.

### On each remote screen

```bash
uv run grydgets-client [--config FILE] [--config-dir DIR]
```

*   `--config`: Client configuration file. Defaults to `client.yaml`.
*   `--config-dir`: The directory containing it. All relative paths are resolved from here.

The client has its own configuration file, `client.yaml`. A sample is included
as `client.yaml.sample`.

```yaml
server:
  url: http://dashboard-host:5000
  token: !secret stream_token   # only if the server sets stream_token
  reconnect_delay: 2
  stale_after: 30
graphics:
  resolution: [1366, 768]
indicator:
  corner: bottom-right
offline:
  enabled: true
  message: Dashboard server unavailable
  clock_format: "%H:%M"
  dim: 0.75
outputs:
  - type: window
    fullscreen: true
```

*   `server.url`: Base URL of the rendering host's HTTP server.
*   `server.token` _(optional)_: Must match the host's `server.auth.stream_token`.
*   `server.reconnect_delay` _(optional)_: Seconds before reconnecting after a dropped connection. Defaults to `2`.
*   `server.stale_after` _(optional)_: How many seconds the connection has to be down before the warning triangle (or the [offline screen](#when-the-server-goes-away)) is shown. Defaults to `30`.
*   `graphics.resolution`: The resolution of this screen. It's sent to the host with every request so that frames arrive already at the right size. If a frame arrives at a different size anyway, it's scaled locally.
*   `logging.level` _(optional)_: `debug`, `info`, or `warning`. Defaults to `info`. `debug` also turns on the [latency overlay](#latency-logginglevel-debug).
*   `indicator.corner` _(optional)_: Which corner the warning triangle is drawn in: `top-left`, `top-right`, `bottom-left`, or `bottom-right`. Defaults to `bottom-right`.
*   `offline.enabled` _(optional)_: Show the [offline screen](#when-the-server-goes-away) instead of the warning triangle. Defaults to `false`.
*   `offline.message` _(optional)_: The text shown under the clock. Defaults to `Dashboard server unavailable`.
*   `offline.clock_format` _(optional)_: `strftime` format for the clock. Defaults to `%H:%M`.
*   `offline.dim` _(optional)_: How much to darken the last frame by, from `0` (not at all) to `1` (completely black). Defaults to `0.75`.
*   `outputs`: Exactly one display output, `window` or `framebuffer`, configured the same way as [on the server](#window).

### When the server goes away

Once the connection has been down for `stale_after` seconds, the client draws a
warning triangle in a corner of the last frame it received. The frame itself is
left as it was, so you can still read an hour-old clock off it. Hopefully you're not late!

If you set `offline.enabled: true`, the screen turns into a clock instead: the
last frame is dimmed by `offline.dim`, and the current time and
`offline.message` are drawn across the middle in white. The triangle isn't
drawn in this case, since the message already says the same thing.

The time is taken from the device's own clock and drawn with a built-in
font, so it doesn't depend on the server or on any font file. It also works if
no frame has ever been received: if you start the client while the server is down, you will see the time on a black background.

### Sizing

You should render at the resolution of your largest screen and let the smaller ones ask for a scaled down frame. Note that this doesn't mean that the host creates multiple canvases, so you don't need to mess with `text_size` or the text size multiplier.

The scaling is done by the rendering host. Each screen sends its
`graphics.resolution` with every request and receives a frame that's already
the right size, so screens of different sizes can share the same stream without
having to scale anything themselves. This matters because scaling is by far the
slowest thing a weak screen has to do: a Raspberry Pi 1 takes about a second to
scale a 1080p frame down to 1366x768, but only about a quarter of that to
display a frame that's already the right size.

`graphics.smooth-scaling` has no effect here: frames are always scaled with
bilinear filtering, because nearest-neighbour scaling makes text unreadable at
these ratios.

### Latency (`logging.level: debug`)

If you need to debug how long it's taking to get an update, you can set `logging.level: debug` in `client.yaml`, and every frame will be displayed
with a small translucent panel in the top-left corner, and the same information
will be written to the log:

```
notice    42 ms
download  18 ms
display    6 ms
total     66 ms
```

*   **notice**: the time between the server publishing the frame and this
    client reading the `/events` line that announced it. This isn't shown for
    the first frame, which is fetched at startup without waiting for an event.
*   **download**: how long the `GET /frame` request took.
*   **display**: the time between the end of the download and the frame being
    ready to display, which includes decoding and scaling.
*   **total**: the sum of the three, i.e. the wall clock time between the
    server publishing a frame and this client showing it.

All four are calculated by comparing this client's clock to the `published_at`
timestamp that the server attaches to the frame (see [`stream`](#stream)), so
they're only

### When the connection drops

The client keeps displaying the last frame it received and tries to reconnect
every `reconnect_delay` seconds. Once the connection has been down for
`stale_after` seconds, it draws an amber warning triangle in a corner (or the offline clock) so that you can tell the frame is old.

If the token is rejected, the triangle is drawn immediately and the client
waits five minutes before trying again, since a bad token isn't going to fix
itself.

### Pushing frames with a `post` output

A [`post` output](#post) uploads each rendered frame to an endpoint configured
in the rendering host's `conf.yaml`. The destination doesn't run a Grydgets
client and never connects to the host, which makes it the right choice for a
device with an upload API, or for a screen that the host can reach but that
can't reach the host.

The main difference from `stream` is which end knows about the other. A `post`
output points at one specific destination, so to add a screen you need to add
another `post` block to the host's `conf.yaml` and reload it with `SIGUSR1`. A
`stream` output, on the other hand, doesn't know anything about who's reading
from it: a new screen just needs to start `grydgets-client` against the host's
URL, and the host's configuration doesn't change.

That leads to a few practical differences:

*   `post` sends frames at the resolution the dashboard is rendered at, so a
    destination that needs a different size has to scale them itself. `stream`
    sends each frame at the size the screen asks for.
*   Each `post` output uploads its own copy of the frame, so the work on the
    host grows with every destination you add.
*   `post` uploads at most once every `min_interval` seconds, so a change can
    take up to that long to show up. `stream` publishes a new frame as soon as
    the dashboard settles, and announces it on `/events`.
*   `post` doesn't need the HTTP server or a `stream_token`. Each destination
    has its own `url` and `auth`.

### Writing your own client

Grydgets ships with its own client, `grydgets-client`, and if that's what
you're using you can skip this section. What follows is a description of the
HTTP API exposed by the [`stream` output](#stream), in case you want to write a
client of your own.

The server exposes two endpoints:

```
GET /frame                        # the current frame, with an ETag
  ?width=1366&height=768          # optional: encode it at this size
  If-None-Match: "a1b2c3-1366x768"  # -> 304 if you already have that one
  X-Frame-Published-At: 1712...   # response header: when this frame was published
GET /events                       # text/event-stream, held open
  ?width=1366&height=768          # optional: logged, so you can see who is connected
  data: {"etag": "d4e5f6", "published_at": 1712...}   # one per published frame
  : ping                          # every 20 seconds
```

A display can ask for frames at its own resolution by passing `width` and
`height`, which is what `grydgets-client` does with its `graphics.resolution`.
You have to pass both or neither: a request with only one of them, or with a
size outside of 1-7680, gets a `400`. If you don't pass them, the frame is
returned at the size the dashboard is rendered at. At most eight different
sizes are served at the same time.

The ETag identifies both the frame and the size, so if you ask for a frame you
already have you get a `304` and don't download anything. A re-render that
produces an identical image keeps the same ETag, so the screen doesn't need to
repaint either. `/frame` returns `503` until the first frame has been
published, and `404` if there is no `stream` output configured.

`published_at` and `X-Frame-Published-At` are both the Unix time at which the
frame was published. `grydgets-client` uses them to measure how long it takes
to notice, download and display a frame (see
[Latency](#latency-logginglevel-debug)). Keep in mind that these measurements
are only meaningful if the clocks of the two machines are in sync, which
Grydgets does nothing to ensure.

```bash
curl -o frame.jpg http://dashboard-host:5000/frame
curl -N http://dashboard-host:5000/events
```

## Hot reload

You can reload the configuration without restarting Grydgets by sending a `SIGUSR1` signal to the running process:

```bash
kill -SIGUSR1 <process_id>
```

This will:
- Stop all existing data providers
- Reload `providers.yaml` and restart providers
- Reload `widgets.yaml` and rebuild the widget tree
- Leave the HTTP server running throughout

## Widget editor

**NOTE: This is highly experimental and likely to be broken!**

A local, browser-based editor for `widgets.yaml`. You can browse the widget
tree, add, remove and reorder children on container widgets, and edit each
widget's properties through forms generated from `schema.json`, without
editing the YAML by hand.

It works, but it's still rough: the forms cover what's in the schema and
nothing more, error handling is thin in places, and the UI hasn't had much
polish. Treat it as a convenience for the common edits rather than a
replacement for opening `widgets.yaml` in an editor.

```bash
uv run grydgets-editor --widgets widgets.yaml
# or: uv run python -m grydgets.editor --widgets widgets.yaml
```

Then open `http://127.0.0.1:5050/` in a browser. Options:

| Flag | Default | Purpose |
|---|---|---|
| `--widgets` | `widgets.yaml` | file to edit |
| `--host` | `127.0.0.1` | bind address |
| `--port` | `5050` | bind port |
| `--debug` | off | Flask debug mode |

Notes:
- The editor only reads and writes the widgets file you point it at. It isn't
  connected to a running dashboard, so you need to reload the dashboard
  yourself after saving (see [Hot Reload](#hot-reload)).
- Saving writes a timestamped backup (`widgets.yaml-YYYYMMDDHHMM.backup`)
  before overwriting the file.
- `!secret` values (and any field containing one, e.g. `auth.bearer`) are
  shown read-only and can't be edited through the editor.
- Theme tokens survive editing. Colour, font path, image path and numeric
  fields have a **value / theme** switch that lets you either pick an entry
  from the matching theme section (`!color panel`, `!font bold`,
  `!image screen`, `!size radius`) or type a plain value. A token on any other
  kind of field is shown as written and left alone. This also applies to the
  screen's own `background_image` and `background_color`.
- A field that gets its value from [`theme.defaults`](#theming) is shown
  greyed out, along with the entry it came from (`from theme: text-like`) and
  the value it resolves to. **Override** copies that value onto the widget so
  you can edit it there, and **remove** drops the override and goes back to
  the theme default. Defaults are never written to the file.
- Schema violations are shown as warnings on save, but they never prevent
  you from saving.
- `rest` and `restimage` widgets have a **Test request** button in their
  inspector. It runs the widget's actual request, with `!secret` values,
  theme tokens and defaults resolved (secrets are shown redacted in the
  panel), and shows you the status code, the raw response, the extracted
  value and the final value. This makes it easy to get `json_path`,
  `jq_expression` and `format_string` right against live data. For a `rest`
  widget you can also tweak the extraction and re-run it against the response
  you already have, without making another request. Keep in mind that testing
  a `POST`, `PUT` or `PATCH` widget sends a real request to the endpoint (the
  panel warns you before doing so). Provider-backed widgets can't be tested
  this way, since they don't make their own HTTP requests.
