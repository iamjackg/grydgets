# Images

## restimage

Fetches an image on a timer and displays it. It can also fetch a JSON document, pull an image URL out of it, and
then fetch that. Both HTTP(S) URLs and local `file://` paths work.

### When you'd want this

Use it for camera snapshots, a weather radar image, a photo that another program updates on disk, or a static logo
or picture (with `static: true`). If the image URL comes from a response that other widgets also read, use a
[`providerimage`](provider-widgets.md#providerimage) instead.

### Parameters

*   `url`: The URL of the image, either `http(s)://` or `file://`.
*   `json_path` _(optional)_: A path to an image URL inside a JSON response. If you set this, `url` is fetched as
    JSON, and the value at this path is fetched as the image. See [Data
    extraction](../configuration/data-extraction.md).
*   `jq_expression` _(optional)_: A jq expression that returns the image URL. If you also set `json_path`, it's
    applied first.
*   `auth` _(optional)_: A bearer token or a username and password for HTTP(S) URLs, see
    [Authentication](../configuration/authentication.md). It isn't used for `file://` URLs.
*   `update_frequency` _(optional)_: How often to fetch the image again, in seconds. Defaults to `30`.
*   `static` _(optional)_: If `true`, the image is only loaded once at startup. Use this for local files or remote
    images that never change. Defaults to `false`.
*   `preserve_aspect_ratio` _(optional)_: If `true`, the image keeps its proportions when it's scaled. If `false`,
    it's stretched to fill the widget. Defaults to `false`.

An image URL extracted from JSON can also be either `http(s)://` or `file://`.

### Examples

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

Since the extracted URL can point at a local file, you can use a jq expression to pick an icon based on a value
from an API. For example, if a weather API returns `"cloudy"`, this shows `images/weather/cloudy.png`:

```yaml
  - widget: restimage
    url: 'https://weather.example.com/tokyo'
    json_path: 'forecast[0].condition'
    jq_expression: '"file://images/weather/" + . + ".png"'
```

## empty

Takes up space without drawing anything, or fills it with a flat colour.

### When you'd want this

Use it to leave a hole in a grid, to push other widgets into place, or, with a `color`, as a divider line or a plain
coloured block.

### Parameters

*   `color` _(optional)_: The colour to fill the widget with, see [Colors](../configuration/colors.md). If you leave
    it out, the widget is fully transparent.
*   `corner_radius` _(optional)_: The corner radius of `color`, in pixels. Defaults to `0`.

### Example

```yaml
  # A faint divider line, in a thin grid row
  - widget: empty
    color: [255, 255, 255, 40]
```
