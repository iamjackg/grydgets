# Colors

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
[Theming](../theming.md).

```yaml
  - widget: dateclock
    time_color: '#eceff4'
    date_color: '#8fbcbb'
    background_color: '#000000a0'
```

If a color can't be parsed, Grydgets fails at load time with an error that
names the parameter. The one exception is a color sent in a
[notification](../widgets/push-widgets.md#notifiabletext) while the dashboard is
running: if it can't be parsed, it's logged and ignored, and the dashboard keeps
going.

## Naming

Similar to CSS, these parameter names mean the same thing on every widget:

*   `color`: the color of the widget's own content, whether that's text, a bar, or the fill of an `empty`.
*   `background_color`: the color painted behind that content.

Anything more specific is prefixed with what it applies to (`time_color`,
`pill_background_color`, `widget_background_color`).
