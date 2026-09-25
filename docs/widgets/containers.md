# Container widgets

Container widgets arrange or decorate other widgets. They all take a `children` list with the widgets they contain.

## grid

Places its children in a grid of rows and columns. Children fill the grid one column at a time: the first child goes
in the top left cell, the second one underneath it, and so on, moving to the next column once the first one is full.

### When you'd want this

Almost always. A grid is how you get more than one widget on the screen, and most dashboards are a few grids nested
inside each other. It's also the easiest way to give a group of widgets matching rounded panels, with
`widget_background_color` and `widget_corner_radius`.

### Parameters

*   `rows`: The number of rows in the grid.
*   `columns`: The number of columns in the grid.
*   `padding` _(optional)_: The gap around each child, in pixels. Defaults to `0`.
*   `background_color` _(optional)_: A color for the grid itself, which shows through between and behind the cells.
    See [Colors](../configuration/colors.md).
*   `widget_background_color` _(optional)_: A color painted behind each child, inside its cell. See
    [Colors](../configuration/colors.md).
*   `widget_background_colors` _(optional)_: Per-cell background colors, overriding `widget_background_color` for the
    cells they name. See [Per-cell overrides](#per-cell-overrides).
*   `corner_radius` _(optional)_: The corner radius of the grid's own background, in pixels. Defaults to `0`.
*   `widget_corner_radius` _(optional)_: The corner radius of each child's background, in pixels. Defaults to `0`.
*   `widget_corner_radii` _(optional)_: Per-cell corner radii, overriding `widget_corner_radius` for the cells they
    name. See [Per-cell overrides](#per-cell-overrides).
*   `image_path` _(optional)_: The path to an image to use as the background of the whole grid.
*   `drop_shadow` _(optional)_: If `true`, draws a drop shadow behind the children. Defaults to `false`.
*   `row_ratios` _(optional)_: The relative height of each row. For example, `[1, 2]` makes the second row twice as
    tall as the first. If you leave it out, all rows are the same height.
*   `column_ratios` _(optional)_: The relative width of each column, the same way. If you leave it out, all columns
    are the same width.

### Example

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

### Per-cell overrides

`widget_background_colors` and `widget_corner_radii` take either a mapping keyed on the `name` of a child, or a list
with one entry per child. Cells that aren't mentioned keep the grid-wide `widget_background_color` or
`widget_corner_radius`. Use these when one tile needs to stand out, like a red background for an alert.

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

## label

Adds a line of text above or below a single child.

### When you'd want this

Use it to say what a number is: a big temperature with a small "Outside" underneath, or a camera image with the
room's name on top. The label always gets a third of the height and the child gets the rest, so the label never
covers the child. It's basically a simpler version of a grid with a very specific purpose.

### Parameters

*   `text`: The text of the label.
*   `font_path` _(optional)_: The path to a `.ttf` file to use for the label.
*   `position` _(optional)_: `above` or `below` the child. Defaults to `above`.
*   `text_size` _(optional)_: The size of the label text in pixels.
*   `color` _(optional)_: The color of the label text, see [Colors](../configuration/colors.md). Defaults to
    `[255, 255, 255]` (white).

### Example

```yaml
  - widget: label
    text: 'Random person'
    position: below
    text_size: 30
    color: [255, 255, 0]
    children:
      - widget: rest # ... some child widget
```

## flip

Cycles through its children, sliding from one to the next at a fixed interval.

### When you'd want this

Use it when you have more to show than room to show it, like a slideshow of camera images, or a panel that
alternates between today's weather and tomorrow's.

!!! warning "Transitions on slow hardware"

    Animated transitions are quite expensive. On slow hardware like a Pi
    Zero, set `transition` to `0` to switch instantly.

### Parameters

*   `interval` _(optional)_: How long each child stays on screen, in seconds. Defaults to `5`.
*   `transition` _(optional)_: How long the slide to the next child takes, in seconds. Set it to `0` to switch
    instantly. Defaults to `1`.
*   `ease` _(optional)_: How much the slide speeds up and slows down. Higher values start and end the slide more
    abruptly. Defaults to `2`.

### Example

```yaml
  - widget: flip
    interval: 5
    transition: 1
    ease: 3
    children:
      - widget: text # first child
      - widget: restimage # second child
```

## scheduleflip

A `flip` that picks which child to show based on the time of day.

### When you'd want this

Use it for things that only matter at certain times: the bus schedule in the morning, the weather for tomorrow in
the evening, or a dimmer, simpler panel overnight.

### Parameters

*   `schedule`: A mapping of `HH:MM` entries matched to the `name` of the child to show from that time until the next one. The
    last entry of the day runs until the first one the next day.
*   `transition` _(optional)_: How long the slide to the next child takes, in seconds. Set it to `0` to switch
    instantly. Defaults to `1`.
*   `ease` _(optional)_: How much the slide speeds up and slows down. Defaults to `2`.

### Example

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

## httpflip

A `flip` that makes its own HTTP request on a timer and picks which child to show based on the response.

### When you'd want this

Use it when something outside the dashboard should decide what's on screen: for example, a Home Assistant template
that returns `True` when the garage door is open, so the flip can switch from the usual camera to the garage one. If several flips need to change based on the same response, use a provider and a
[`providerflip`](provider-widgets.md#providerflip) instead.

### Parameters

*   `url`: The URL to request.
*   `mapping`: A mapping of response values to the `name` of the child to show for each one.
*   `default_widget`: The `name` of the child to show when the response doesn't match anything in `mapping`.
*   `json_path` _(optional)_: A path to the value to compare, see [Data
    extraction](../configuration/data-extraction.md). If you don't set this or `jq_expression`, the raw response text
    is used.
*   `jq_expression` _(optional)_: A jq expression that returns the value to compare. If you also set `json_path`, it's
    applied first.
*   `auth` _(optional)_: A bearer token or a username and password, see
    [Authentication](../configuration/authentication.md).
*   `method` _(optional)_: `GET` or `POST`. Defaults to `GET`.
*   `payload` _(optional)_: A JSON body to send with a `POST` request.
*   `update_frequency` _(optional)_: How often to make the request, in seconds. Defaults to `30`.
*   `static` _(optional)_: If `true`, the request is only made once at startup. Defaults to `false`.
*   `transition` _(optional)_: How long the slide to the next child takes, in seconds. Set it to `0` to switch
    instantly. Defaults to `1`.
*   `ease` _(optional)_: How much the slide speeds up and slows down. Defaults to `2`.

### Example

```yaml
  - widget: httpflip
    default_widget: main-cam
    update_frequency: 60
    url: "https://homeassistant.example.com/api/template"
    method: POST
    auth:
      bearer: !secret hass_token
    payload:
      template: '{{ is_state("cover.garage_door", "open") }}'
    mapping:
      "False": main-cam
      "True": garage-cam
    children:
      - widget: restimage
        name: main-cam
        url: http://192.168.255.34/image.jpg
      - widget: restimage
        name: garage-cam
        url: 'https://motioneye.example.com/picture/13/current'
```

## pill

Draws its second child in a pill-shaped badge on top of its first child.

### When you'd want this

Use it to put a small status on top of a picture: someone's name or "Home" / "Away" on their profile picture, or a
temperature on a camera image. With `circular_mask`, the picture gets cropped into a circle, like an avatar.

### Parameters

*   `children`: Exactly two children. The first one is the base, and the second one is drawn inside the pill.
*   `circular_mask` _(optional)_: If `true`, crops the base child into a circle. Defaults to `false`.
*   `widget_background_color` _(optional)_: A color painted behind the base child when `circular_mask` is on. See
    [Colors](../configuration/colors.md).
*   `pill_background_color` _(optional)_: The color of the pill. See [Colors](../configuration/colors.md). Defaults
    to transparent.
*   `pill_width_percent` _(optional)_: The width of the pill, as a fraction of the container's width. Defaults to
    `0.8`.
*   `pill_height_percent` _(optional)_: The height of the pill, as a fraction of the container's height. Defaults to
    `0.2`.
*   `pill_position_x` _(optional)_: Where the center of the pill goes horizontally, from `0.0` (left edge) to `1.0`
    (right edge). Defaults to `0.5`.
*   `pill_position_y` _(optional)_: Where the center of the pill goes vertically, from `0.0` (top) to `1.0` (bottom).
    Defaults to `0.8`.
*   `pill_corner_radius` _(optional)_: The corner radius of the pill, in pixels. If you leave it out, the ends are
    fully rounded.
*   `pill_size_relative_to_circle` _(optional)_: If `true` and `circular_mask` is on, the pill's size is a fraction
    of the circle's diameter instead of the container's size. Use this when a round picture sits in a wide cell, and
    you want the pill to line up with the picture rather than stretch across the whole cell. Defaults to `false`.

### Example

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
