# Dashboard layout (`widgets.yaml`)

`widgets.yaml` describes the dashboard itself: which widgets there are, how they're laid out, and where they get
their data from. A sample file is included in the repository.

Every widget is a mapping with a `widget` key that names its type, followed by the parameters for that type. Container
widgets take a `children` list, and nesting them builds the tree. The root is usually a [`grid`](../widgets/containers.md#grid):

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

Every widget type and its parameters are described under [Widgets](../widgets/index.md).

The top level of the file configures the screen itself, which acts as a container for the whole dashboard:

*   `background_image` _(optional)_: The path to an image file to use as the background for the entire screen. Takes precedence over `background_color`. Can be a theme token, see [Theming](../theming.md).
*   `background_color` _(optional)_: A color for the screen background, see [Colors](colors.md). Used when there is no `background_image`. Defaults to `[0, 0, 0]` (black).
*   `drop_shadow` _(optional)_: If `true`, draws a drop shadow behind the dashboard's content. This helps text stay readable on top of a busy `background_image`. Defaults to `false`.
*   `widgets`: A list containing the root widget of your dashboard, see [Widgets](../widgets/index.md). The screen only supports a single child for now, so if you want more than one widget on screen, make the root a `grid`.
*   `theme` _(optional)_: Named values and per-widget defaults, see [Theming](../theming.md).
