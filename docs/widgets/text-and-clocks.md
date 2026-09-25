# Text and clocks

## text

Displays a fixed string.

### When you'd want this

Use it for anything that doesn't change: a title, a room name, a separator character, or a placeholder while you're
laying out a dashboard. If the text needs to come from somewhere, use [`rest`](#rest) or a
[`provider`](provider-widgets.md#provider) widget instead.

### Parameters

*   `text` _(optional)_: The text to display. Defaults to an empty string.
*   `text_size` _(optional)_: The size of the text in pixels. If you leave it out, the text grows to fit the widget.
*   `font_path` _(optional)_: The path to a `.ttf` file to use. If you leave it out, PyGame's default font is used.
*   `color` _(optional)_: The color of the text, see [Colors](../configuration/colors.md). Defaults to
    `[255, 255, 255]` (white).
*   `background_color` _(optional)_: A color painted behind the text, see [Colors](../configuration/colors.md). It
    covers the whole widget, and `padding` only moves the text inward. If you leave it out, the widget is transparent.
*   `corner_radius` _(optional)_: The corner radius of `background_color`, in pixels. Defaults to `0`.
*   `padding` _(optional)_: The gap around the text, in pixels. Defaults to `0`.
*   `align` _(optional)_: The horizontal alignment: `left`, `center`, or `right`. Defaults to `left`.
*   `vertical_align` _(optional)_: The vertical alignment: `top`, `center`, or `bottom`. Defaults to `top`.

If you give a text widget its own `background_color`, you don't need to wrap it in a `grid` to give it a panel.

### Example

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

## dateclock

Displays a 24-hour clock, with the current date underneath.

### When you'd want this

Use it whenever you want the time and date on the dashboard. The time and the date are drawn as separate lines with their own font and color, so you can do cool stuff like use a serif display font for the time
and a sans-serif one for the date.

### Parameters

*   `time_font_path`: The path to a `.ttf` file to use for the time.
*   `date_font_path`: The path to a `.ttf` file to use for the date.
*   `color` _(optional)_: The color of both lines, see [Colors](../configuration/colors.md). Defaults to
    `[255, 255, 255]` (white).
*   `time_color` _(optional)_: The color of the time only. Overrides `color` for the time.
*   `date_color` _(optional)_: The color of the date only. Overrides `color` for the date.
*   `background_color` _(optional)_: A color painted behind the clock, see [Colors](../configuration/colors.md).
*   `corner_radius` _(optional)_: The corner radius of `background_color`, in pixels. Defaults to `0`.

### Example

```yaml
  - widget: dateclock
    time_font_path: 'fonts/Fraunces-700.ttf'
    date_font_path: 'fonts/Inter-400.ttf'
    time_color: [236, 239, 244]
    date_color: [143, 188, 187]
    background_color: [0, 0, 0, 160]
    corner_radius: 25
```

## rest

Makes an HTTP request on a timer and displays the response as text. It can pull a single value out of a JSON
response and wrap it in a format string.

### When you'd want this

Use it to show a single value from an API: a temperature, a stock price, the state of a Home Assistant sensor. If
several widgets need values from the same response, set up a [provider](../configuration/providers-yaml.md) instead,
so the request is only made once.

### Parameters

*   `url`: The URL to request.
*   `json_path` _(optional)_: A path to the value to show, like `address.city` or `items[0].name`. See [Data
    extraction](../configuration/data-extraction.md).
*   `jq_expression` _(optional)_: A jq expression that returns the value to show, like `.items[] | select(.active)`.
    If you also set `json_path`, it's applied first.
*   `format_string` _(optional)_: A Python format string for the final text, with `{}` standing in for the value.
    Defaults to `{}`.
*   `method` _(optional)_: `GET` or `POST`. Defaults to `GET`.
*   `payload` _(optional)_: A JSON body to send with a `POST` request.
*   `auth` _(optional)_: A bearer token or a username and password, see
    [Authentication](../configuration/authentication.md).
*   `update_frequency` _(optional)_: How often to make the request, in seconds. Defaults to `30`.
*   `static` _(optional)_: If `true`, the request is only made once at startup. Use this for values that don't
    change while the dashboard is running. Defaults to `false`.
*   `font_path` _(optional)_: The path to a `.ttf` file to use. If you leave it out, PyGame's default font is used.
*   `text_size` _(optional)_: The size of the text in pixels. If you leave it out, the text grows to fit the widget.
*   `color` _(optional)_: The color of the text, see [Colors](../configuration/colors.md). Defaults to
    `[255, 255, 255]` (white).
*   `background_color` _(optional)_: A color painted behind the text, see [Colors](../configuration/colors.md). It
    covers the whole widget, and `padding` only moves the text inward. If you leave it out, the widget is transparent.
*   `corner_radius` _(optional)_: The corner radius of `background_color`, in pixels. Defaults to `0`.
*   `padding` _(optional)_: The gap around the text, in pixels. Defaults to `6`.
*   `align` _(optional)_: The horizontal alignment: `left`, `center`, or `right`. Defaults to `center`.
*   `vertical_align` _(optional)_: The vertical alignment: `top`, `center`, or `bottom`. Defaults to `center`.

### Example

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
