# Provider widgets

Provider widgets read their data from a shared provider defined in
[`providers.yaml`](../configuration/providers-yaml.md), instead of making their own HTTP requests. Several widgets
can read the same provider, and the data is only fetched once.

A provider widget updates every time its provider fetches new data, even if the data turns out to be the same as
last time.

## provider

Displays a value from a provider as text.

### When you'd want this

It's the provider version of [`rest`](text-and-clocks.md#rest). Use it when you're showing several values from the
same response, like the title, location and start time of the next calendar event.

If your data lives in Home Assistant, you can also use a provider to render a Home Assistant template: POST it to
`/api/template`, like in the [`providerflip` example](#providerflip), and show the result with a `provider` widget.
The template can read any entity in Home Assistant, so you can combine several of them into one line of text.

### Parameters

*   `providers`: A list with exactly one provider name, like `[hass_calendar]`.
*   `data_path` _(optional)_: A path to the value to show, see [Data
    extraction](../configuration/data-extraction.md).
*   `jq_expression` _(optional)_: A jq expression that returns the value to show. If you also set `data_path`, it's
    applied first.
*   `format_string` _(optional)_: A Python format string for the final text, with `{value}` standing in for the
    value. Defaults to `"{value}"`.
*   `fallback_text` _(optional)_: The text to show if there's an error or no data. Defaults to `"--"`.
*   `show_errors` _(optional)_: If `true`, shows the error message instead of `fallback_text`. Handy while you're
    setting things up. Defaults to `false`.
*   `font_path` _(optional)_: The path to a `.ttf` file to use.
*   `text_size` _(optional)_: The size of the text in pixels. If you leave it out, the text grows to fit the widget.
*   `color` _(optional)_: The colour of the text, see [Colors](../configuration/colors.md). Defaults to
    `[255, 255, 255]` (white).
*   `background_color` _(optional)_: A colour painted behind the text, see [Colors](../configuration/colors.md). It
    covers the whole widget, and `padding` only moves the text inward. If you leave it out, the widget is transparent.
*   `corner_radius` _(optional)_: The corner radius of `background_color`, in pixels. Defaults to `0`.
*   `padding` _(optional)_: The gap around the text, in pixels. Defaults to `6`.
*   `align` _(optional)_: The horizontal alignment: `left`, `center`, or `right`. Defaults to `center`.
*   `vertical_align` _(optional)_: The vertical alignment: `top`, `center`, or `bottom`. Defaults to `center`.

### Example

```yaml title="providers.yaml"
providers:
  my_calendar:
    type: rest
    url: !secret calendar_api
    update_interval: 60
```

```yaml title="widgets.yaml"
widgets:
  - widget: grid
    rows: 3
    columns: 1
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

## providerflip

A `flip` that picks which child to show based on data from a provider.

### When you'd want this

It's the provider version of [`httpflip`](containers.md#httpflip). Use it when the value that decides what's on
screen comes from a response that other widgets also read, or when you want several flips to switch on the same
value.

### Parameters

*   `providers`: A list with exactly one provider name.
*   `data_path` _(optional)_: A path to the value to compare.
*   `jq_expression` _(optional)_: A jq expression that returns the value to compare.
*   `mapping`: A mapping of values to the `name` of the child to show for each one.
*   `default_widget`: The `name` of the child to show at startup, and whenever the value doesn't match anything in
    `mapping`.
*   `transition` _(optional)_: How long the slide to the next child takes, in seconds. Set it to `0` to switch
    instantly. Defaults to `1`.
*   `ease` _(optional)_: How much the slide speeds up and slows down. Defaults to `2`.

The provider is checked on every frame, so `interval` doesn't have any effect here. If the provider returns an
error, the widget keeps showing whatever child it was already showing. The values in `mapping` are compared as
strings, so a JSON `true` has to be written as `"True"`.

### Example

```yaml title="providers.yaml"
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
```

```yaml title="widgets.yaml"
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

## providerimage

Displays an image whose URL comes from provider data. Both HTTP(S) URLs and local `file://` paths work.

### When you'd want this

It's the provider version of [`restimage`](images.md#restimage). Use it when the image URL is part of a response
that other widgets also read, like a weather icon next to a temperature from the same forecast.

### Parameters

*   `providers`: A list with exactly one provider name.
*   `data_path` _(optional)_: A path to the image URL.
*   `jq_expression` _(optional)_: A jq expression that returns the image URL.
*   `fallback_image` _(optional)_: The path to an image to show if there's an error.
*   `auth` _(optional)_: A bearer token or a username and password for fetching HTTP(S) images, see
    [Authentication](../configuration/authentication.md). It isn't used for `file://` URLs.
*   `preserve_aspect_ratio` _(optional)_: If `true`, the image keeps its proportions when it's scaled. If `false`,
    it's stretched to fill the widget. Defaults to `false`.
*   `show_errors` _(optional)_: If `true`, shows the error message instead of `fallback_image`. Defaults to `false`.

### Example

```yaml title="providers.yaml"
providers:
  camera_urls:
    type: rest
    url: https://api.example.com/cameras
    json_path: "active_cameras"
    update_interval: 30
```

```yaml title="widgets.yaml"
  - widget: providerimage
    providers: [camera_urls]
    data_path: "[0].image_url"
    fallback_image: "camera_offline.png"

  # With a provider that returns {"current_image": "file:///home/user/images/photo.jpg"}
  - widget: providerimage
    providers: [local_images]
    data_path: "current_image"
```

Since the URL can point at a local file, you can use a jq expression to pick an icon based on a value from the
provider. For example, if the forecast says `"cloudy"`, this shows `images/weather/cloudy.png`:

```yaml
  - widget: providerimage
    providers: [hourly_weather_api]
    data_path: 'forecast[0].condition'
    jq_expression: '"file://images/weather/" + . + ".png"'
```

## providerbarchart

Draws a bar chart from a list of numbers in provider data. It's deliberately minimal, with no axes or legend. I had to draw the line somewhere.

### When you'd want this

Use it for a quick sense of how something changes over time, like the chance of rain for each of the next 24 hours,
or energy use per day for the last week. The bars can be coloured by value, and you can add optional labels
underneath and guide lines behind them.

### Parameters

*   `providers`: A list with exactly one provider name.
*   `data_path` _(optional)_: A path to the list of values.
*   `jq_expression` _(optional)_: A jq expression that returns a JSON array of numbers.
*   `bar_color` _(optional)_: The default colour of the bars, see [Colors](../configuration/colors.md). Defaults to
    `[100, 149, 237]` (cornflower blue).
*   `bar_colors` _(optional)_: A mapping of labels to colours. A bar whose label matches a key is drawn in that
    colour, regardless of `bar_color_thresholds` and `bar_color`.
*   `bar_color_thresholds` _(optional)_: A list of `{above: <value>, color: <color>}` entries. Each bar gets the
    colour of the highest threshold that its value is at or above. If it's below all of them, it gets `bar_color`.
*   `bar_background_colors` _(optional)_: A mapping of labels to colours. The matching bar gets a full-height
    rectangle of that colour behind it. Use this to mark specific bars, like midnight on an hourly chart: the
    background is visible even when the bar's value is zero.
*   `bar_gap` _(optional)_: The gap between bars, in pixels. Defaults to `2`.
*   `max_value` _(optional)_: The value at the top of the chart. If you leave it out, the chart scales to the largest
    value in the data. Set it when the values have a natural maximum, like `100` for percentages, so that a quiet day
    doesn't look like a busy one.
*   `min_value` _(optional)_: The value at the bottom of the chart. Defaults to `0`.
*   `midline` _(optional)_: If `true`, draws a horizontal line at the halfway point, behind the bars. Defaults to
    `false`.
*   `midline_thickness` _(optional)_: The thickness of the midline, in pixels. Defaults to `1`.
*   `midline_color` _(optional)_: The colour of the midline, see [Colors](../configuration/colors.md). Defaults to
    `[255, 255, 255]` (white).
*   `quartline` _(optional)_: If `true`, draws horizontal lines at the 25% and 75% points, behind the bars. Defaults
    to `false`.
*   `quartline_thickness` _(optional)_: The thickness of the quartlines, in pixels. Defaults to `1`.
*   `quartline_color` _(optional)_: The colour of the quartlines, see [Colors](../configuration/colors.md). Defaults
    to `[255, 255, 255]` (white).
*   `labels_jq_expression` _(optional)_: A jq expression that returns a JSON array of strings, one label per bar.
*   `labels_data_path` _(optional)_: A path to the list of labels, if you don't need jq for them.
*   `label_font_path` _(optional)_: The path to a `.ttf` file to use for the labels.
*   `label_size` _(optional)_: The size of the labels, in pixels. Defaults to `12`.
*   `label_color` _(optional)_: The colour of the labels, see [Colors](../configuration/colors.md). Defaults to
    `[200, 200, 200]`.

### Example

Hourly chance of rain for the next 24 hours, with a faint highlight behind midnight:

```yaml title="providers.yaml"
providers:
  hourly_weather:
    type: rest
    url: https://weather.example.com/api/hourly
    update_interval: 3600
```

```yaml title="widgets.yaml"
  - widget: providerbarchart
    providers: [hourly_weather]
    jq_expression: "[.forecast[:24][].precipitation_probability]"
    labels_jq_expression: "[.forecast[:24][].datetime | .[11:13]]"  # the hour digits of each timestamp
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
