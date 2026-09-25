# Remote displays

You can render the dashboard on one machine and display it on another. The
rendering machine runs Grydgets with a [`stream` output](configuration/conf-yaml.md#stream), and each
screen runs `grydgets-client`, which connects to it, fetches a new frame
whenever one is published, and displays it. Remote screens only show pictures, so
they don't need a `widgets.yaml`, providers, fonts or images of their own.

This is useful when the screen devices are too slow to render the dashboard
themselves. A big dashboard with hundreds of widgets at 1080p can take a Raspberry Pi so long to
draw that the clock might end up half a minute late, while a desktop can draw it quickly and
run at a higher `fps-limit`.

If you have a display device that can't run `grydgets-client` but it accepts some form of image upload, like a WiFi photo frame or a signage box, you can push frames to it with a [`post` output](#pushing-frames-with-a-post-output) instead.

## On the rendering host

Add a `stream` output, and configure the server to bind to an address that the screens can
reach.

```yaml
graphics:
  fps-limit: 10
  resolution: [1920, 1080]
server:
  host: 0.0.0.0
  port: 5000
  auth:
    stream_token: !secret stream_token  # this is optional
outputs:
  - type: stream
    image_format: jpeg
```

Since there's no display output, the rendering host doesn't need a screen of
its own. A single Grydgets process can serve multiple remote screens, all with different resolutions. It's a good idea to configure the rendering host to render at the highest dashboard resolution you're going to display, since downscaling looks nicer than upscaling.

## On each remote screen

```bash
grydgets-client [--config FILE] [--config-dir DIR]
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
*   `graphics.resolution`: The resolution of this screen. It's sent to the host with every request so that frames arrive already at the right size.
*   `logging.level` _(optional)_: `debug`, `info`, or `warning`. Defaults to `info`. `debug` also turns on the [latency overlay](#measuring-latency).
*   `indicator.corner` _(optional)_: Which corner the warning triangle is drawn in: `top-left`, `top-right`, `bottom-left`, or `bottom-right`. Defaults to `bottom-right`.
*   `offline.enabled` _(optional)_: Show the [offline screen](#when-the-server-goes-away) instead of the warning triangle. Defaults to `false`.
*   `offline.message` _(optional)_: The text shown under the offline screen's clock. Defaults to `Dashboard server unavailable`.
*   `offline.clock_format` _(optional)_: `strftime` format for the offline screen's clock. Defaults to `%H:%M`.
*   `offline.dim` _(optional)_: How much to darken the last succesfully downloaded frame in the background when displaying the offline screen, from `0` (not at all) to `1` (completely black). Defaults to `0.75`.
*   `outputs`: Exactly one `window` output, configured the same way as [on the server](configuration/conf-yaml.md#window). On a device without a desktop, see [Running without a desktop](configuration/conf-yaml.md#running-without-a-desktop).

## When the server goes away

If the connection drops, the client keeps displaying the last frame it
received and tries to reconnect every `reconnect_delay` seconds. Once the
connection has been down for `stale_after` seconds, it draws an amber warning
triangle in a corner of the frame, so you can tell that what you're looking at
is old. The frame itself is left as it was, so you can still read your nice hour-old
clock off it. Hopefully you're not late!

If you set `offline.enabled: true`, the screen turns into a clock instead: the
last frame is dimmed by `offline.dim`, and the current time and
`offline.message` are drawn across the middle in white. The triangle isn't
drawn in this case, since the message already says the same thing.

The time is taken from the device's own clock and drawn with a built-in font,
so it keeps working without the server or any font files. If you start the
client while the server is down, you'll see the time on a black background.

If the server rejects the token, the client shows the warning right away and
waits five minutes before trying again.

## Sizing

Render the dashboard at the resolution of your largest screen, and let the
smaller ones ask for a scaled-down copy. That way the layout is only drawn once, at the
host's resolution, and then shrunk for each screen direclty on the host itself, so you don't need to adjust
`text_size` or `text-scale` for the smaller ones. This also helps a lot on weak hardware, where down- or upscaling a large frame can take much longer than displaying it.

`graphics.smooth-scaling` doesn't have any effect on these frames: they're
always scaled with bilinear filtering.

## Measuring latency

If you want to see how long it takes for an update to reach a screen, set
`logging.level: debug` in `client.yaml`. Every frame will be displayed with a
small translucent panel in the top-left corner, and the same numbers will be
written to the log:

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
timestamp that the server attaches to the frame (see
[`stream`](configuration/conf-yaml.md#stream)), so they're only meaningful if
the clocks of the two machines are in sync. Grydgets doesn't do anything to
sync them, so you'll want NTP or something similar running on both.

## Pushing frames with a `post` output

The [`post` output](configuration/conf-yaml.md#post) uploads each rendered frame
to an endpoint configured in the rendering host's `conf.yaml`. The destination
doesn't run a Grydgets client and never connects to the host. Use it for a
device that has some kind of upload API.

Note that `post` sends frames at the resolution the dashboard is rendered at, so if your destination needs a different size it has to scale them itself.

Also important: `post` uploads at most once every `min_interval` seconds, so a change can take up to that long to show up.

## Writing your own client

Grydgets ships with its own client, `grydgets-client`, and if that's what
you're using you can skip this section. What follows is a description of the
HTTP API exposed by the [`stream` output](configuration/conf-yaml.md#stream), in case you want to write a
client of your own.

The server exposes an `/events` endpoint you should "subscribe" to:

```
GET /events                       # returns a stream of events using text/event-stream, held open
  ?width=1366&height=768          # optional: gets logged on the host, so you can see who is connected

Example returned data:  
  data: {"etag": "d4e5f6", "published_at": 1712...}   # one per published frame
  : ping                          # every 20 seconds
```

The idea is that whenever you receive an event telling you that there's a new frame, you can request that frame:

```
GET /frame                        # reeturns the current frame, with a unique ETag
  ?width=1366&height=768          # optional: encode it at this size
  
You can optionally supply this header:  
  If-None-Match: "a1b2c3-1366x768"  # -> gives you a 304 if nothing has changed since that etag and resolution combo

The response will contain this header:
  X-Frame-Published-At: 1712...   # timestamp for when this frame was originally published
```

Displays can ask for frames at their own resolution by passing `width` and
`height`, which is what `grydgets-client` does with its `graphics.resolution`.
You have to pass both or neither: a request with only one of them, or with a
size outside of 1-7680, gets a `400`. If you don't pass them, the frame is
returned at the size the dashboard is rendered at. At most eight different
sizes can be served at the same time.

The ETag identifies both the frame and the size, so if you ask for a frame you
already have you get a `304` and don't download anything. If a re-render
produces an identical image, the ETag stays the same, so your client can skip
repainting the screen too. `/frame` returns `503` until the first frame has
been published, and `404` if there is no `stream` output configured.

`published_at` and `X-Frame-Published-At` are both the Unix time at which the
frame was published. `grydgets-client` uses them to [measure
latency](#measuring-latency) in debug mode.

```bash
curl -o frame.jpg http://dashboard-host:5000/frame
curl -N http://dashboard-host:5000/events
```
