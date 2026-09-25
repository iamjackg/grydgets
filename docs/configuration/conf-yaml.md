# `conf.yaml`

Every top-level key of `conf.yaml` is described below. `graphics` and
`logging` are required, the others are optional.

## `graphics`

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
*   `smooth-scaling` _(optional)_: Use bilinear filtering when scaling images (`true`, the default) or the faster but uglier nearest-neighbor (`false`). Set it to `false` on slow hardware like a Raspberry Pi 2.
*   `flip` _(optional)_: Rotates the output 180 degrees. Defaults to `false`.
*   `text-scale` _(optional)_: A multiplier applied to every text size in `widgets.yaml`, see below. Defaults to `1.0`.

### Using the same widgets file on two screens

`text_size` is specified in pixels, so the same value can look wonky on screens with different resolutions. If you
want to use the same `widgets.yaml` on several screens, set `text-scale` in each screen's `conf.yaml` to the height of
the screen divided by the height the widgets were designed for. For example, widgets written for a 768 pixel tall
screen need `1.4` on a 1080p one:

```yaml
graphics:
  resolution: [1920, 1080]
  text-scale: 1.4
```

Only `text_size` is scaled. Widgets without a `text_size` auto-fit their contents, so they already grow with the
resolution. `padding` and `corner_radius` aren't scaled.

## `logging`

The `logging:` block controls how much Grydgets writes to the log.

```yaml
logging:
  level: info
```

*   `level`: `debug`, `info`, or `warning`. Defaults to `info`.

## `outputs`

Outputs determine where the rendered dashboard goes: a window, a file on disk, or another machine. You can configure one or more of them with an `outputs` list in `conf.yaml`:

```yaml
outputs:
  - type: window
    fullscreen: true
```

If no `outputs` key is present, Grydgets falls back to legacy behavior based on the `graphics` and `headless` keys (see [Legacy configuration](#legacy-configuration)).

You need at least one output. You can have at most one `window` output, and as many of the others (`file`, `post`,
`stream`) as you like. If you don't configure a `window`, Grydgets doesn't need a screen at all, so you can run it on a
headless machine.

### window

Displays the dashboard in an SDL window.

*   `fullscreen` _(optional)_: Run in fullscreen mode. Defaults to `false`.
*   `x_display` _(optional)_: The X display to use (e.g. `":0"`). You only need this if you're starting Grydgets over SSH.

```yaml
outputs:
  - type: window
    fullscreen: true
    x_display: ":0"
```

#### Running without a desktop

On a machine without a desktop, like a Raspberry Pi booted to the console, set `fullscreen: true` and start Grydgets
as usual. When [SDL](https://www.libsdl.org/) (the library PyGame uses to talk to the screen) can't find a desktop, it
falls back to drawing on the screen directly through [KMS/DRM](https://en.wikipedia.org/wiki/Direct_Rendering_Manager),
and the window takes over the whole screen. Your user needs to be in the `video` and `render` groups, and nothing else
can be using the screen at the same time.

!!! warning "Starting Grydgets over SSH"

    If your SSH session has X forwarding turned on, SDL will find that desktop first and open the window on the machine
    you're connecting from. Connect without it (`ssh -x`), or start Grydgets with `SDL_VIDEODRIVER=kmsdrm` to make SDL
    skip the desktop check.

### file

Saves a rendered image to disk at a regular interval. Use this if you want to serve the dashboard from a web server, or to make a timelapse.

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

### post

Pushes the rendered image via HTTP POST to a remote endpoint. Works with any device or service that accepts image uploads: networked displays, smart signage, ingestion APIs, and so on.

*   `url`: The endpoint to POST to.
*   `image_format` _(optional)_: `png`, `jpg`, `jpeg`, or `bmp`. Defaults to `"png"`.
*   `trigger` _(optional)_: When to push. `"on_dirty"` only pushes when content has changed. `"interval"` pushes on a fixed schedule regardless. Defaults to `"on_dirty"`.
*   `min_interval` _(optional)_: Minimum seconds between pushes. Defaults to `60`.
*   `auth` _(optional)_: Authentication. Supports `bearer` token or `basic` username/password.
*   `multipart` _(optional)_: Send the image as a `multipart/form-data` upload instead of raw bytes. Required for endpoints that expect a browser-style file upload.
    *   `field_name` _(optional)_: The form field name. Defaults to `"file"`.
    *   `filename` _(optional)_: The filename reported in the upload. Defaults to `image.<format>` (e.g. `image.jpeg`).
*   `after_post` _(optional)_: An additional HTTP request to make after a successful upload. Some devices need a separate "apply" or "display" call before they show the uploaded image, and this is where it goes.
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

### stream

Streams the latest frame to [remote displays](../remote-displays.md) over the [HTTP server](#server), and tells them
as soon as a new one is ready. Adding this output starts the server, and frames are served from the same port as
`/notify` and `/theme`.

Grydgets ships with `grydgets-client`, a built-in client for this. See [Remote displays](../remote-displays.md).

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

When something on the dashboard changes, a new frame is only published once the dashboard has stayed still for
`debounce_ms`. This means that remote displays don't show animations like `flip` transitions: they only update once
things have stopped moving. It's a little odd, but in practice I always turn off transitions in my dashboards anyway.

If you want to write your own client, the HTTP API is described under [Writing your own
client](../remote-displays.md#writing-your-own-client).

### Combining outputs

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

### Legacy configuration

Grydgets still accepts the display settings under `graphics` and the `headless` key from older versions, and turns them into outputs like this:

*   `headless.enabled: true` becomes a `file` output
*   Otherwise, a `window` output is created from `graphics.fullscreen`

If you add an `outputs` key, the legacy display settings (`fullscreen`, `x-display`) and `headless` block are ignored.

!!! warning "Changing the display mode needs a restart"

    If you hot reload (`SIGUSR1`) a change that switches between a display and a non-display mode,
    Grydgets will warn you and skip it.

## `server`

The `server:` block configures the HTTP server, which is used by a few features. Note that having this section in
the config doesn't start the server on its own: it's only started if at least one of these features is in use:

| Feature | Endpoint it needs |
|---|---|
| A [notifiable widget](../widgets/push-widgets.md#notifiabletext) in `widgets.yaml` | `/notify` |
| A [`stream` output](#stream) | `/frame`, `/events` |
| [`appearance.http_control: true`](#appearance-day-and-night-themes) | `/theme` |

If none of the three features above are in use, Grydgets doesn't open
any ports and the `server:` block is ignored.

*   `host` _(optional)_: The address to bind to. Defaults to `127.0.0.1`, which
    is only reachable from the machine running Grydgets. Set it to `0.0.0.0` or
    to a LAN address if the server needs to be called from another machine, for
    example by a [remote display](../remote-displays.md) fetching frames or by Home
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

!!! warning "Set a `control_token` if the port isn't private"

    Without one, anyone who can reach the port can call `/notify`. That endpoint fetches an image
    from whatever URL is in the request body, so they can make your dashboard display anything they
    like.

If you [hot reload](../hot-reload.md) a configuration change that removes a feature
that uses an endpoint, that endpoint will stop being available and will return
a `404`. Starting or stopping the server itself requires a restart though, and Grydgets
will warn you if a reload would have changed that.

## `appearance`: day and night themes

The `appearance:` block in `conf.yaml` names two [theme files](../theming.md#theme-files)
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
*   `latitude`, `longitude` _(optional, but both or neither)_: Decimal degrees, north and east positive. Sunrise and sunset are calculated locally, so the dashboard switches on time even without a network connection. Leave them out if you only want to switch themes over [HTTP](../theming.md#setting-the-theme-over-http).
*   `offsets` _(optional)_: Minutes to move each boundary by, negative for earlier. Defaults to `0`.
*   `default` _(optional)_: The theme to use at startup, `day` or `night`. It's also the theme used on days when the sun doesn't rise or set (e.g. if you're close to the poles). Defaults to `day`.
*   `http_control` _(optional)_: Enables the [`/theme` endpoint](../theming.md#setting-the-theme-over-http), which means the HTTP server gets started. Defaults to `false`.

If you don't provide coordinates, the [`/theme` endpoint](../theming.md#setting-the-theme-over-http)
becomes the only way to change the theme. Use this if you want something else
to decide, like a Home Assistant automation that watches a light sensor or
checks whether anybody is home. You'll need to set
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

!!! tip

    The coordinates don't need to be precise: being off by a degree moves sunset by about four
    minutes.

At startup and at every switch, Grydgets logs what it thinks the sun is doing.
This is the quickest way to check that the coordinates are right:

```
Sun at 45.12,-75.34: day from 05:57 to 19:45 local (offsets +0/-30 min); night theme at 19:45
```

You can also force a specific theme, or go back to following the sun, through
the [HTTP server](../theming.md#setting-the-theme-over-http). That's the easiest way to check what both
themes look like without waiting for dusk.
