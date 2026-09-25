# Widgets

Grydgets, as the name suggests, draws dashboards out of _widgets_. They come in two kinds:

*   **Normal widgets** draw something on the screen: a clock, the result of a REST call, an image, and so on.
*   **Container widgets** decide where and how other widgets appear. A `grid`, for example, lays its children out in
    rows and columns, and a `label` adds a caption above or below its child.

Every widget page lists the widget's parameters, a "When you'd want this" section, and an example.

## Parameters every widget takes

*   `name` _(optional)_: A name for this widget. It shows up in the logs, and it's how other widgets and requests
    refer to this one: a `flip` or a grid's per-cell overrides pick children by `name`, and a notification is sent to
    a notifiable widget by its `name`. Defaults to the widget type.

## Every widget

**Containers.** They arrange or decorate other widgets, and all of them take a `children` list.

| Widget | What it does |
|---|---|
| [`grid`](containers.md#grid) | Lays its children out in a grid, with padding, backgrounds and rounded corners |
| [`label`](containers.md#label) | Adds a text label above or below a single child |
| [`flip`](containers.md#flip) | Cycles through its children at a fixed interval, with a transition |
| [`scheduleflip`](containers.md#scheduleflip) | A `flip` that picks a child based on the time of day |
| [`httpflip`](containers.md#httpflip) | A `flip` that picks a child based on the response to an HTTP request |
| [`pill`](containers.md#pill) | Draws a pill-shaped badge on top of a single child |

**Text and clocks.**

| Widget | What it does |
|---|---|
| [`text`](text-and-clocks.md#text) | Displays a fixed string |
| [`dateclock`](text-and-clocks.md#dateclock) | A 24-hour clock with the date underneath |
| [`rest`](text-and-clocks.md#rest) | Makes its own periodic HTTP request and displays the response |

**Images.**

| Widget | What it does |
|---|---|
| [`restimage`](images.md#restimage) | Periodically fetches an image and displays it |
| [`empty`](images.md#empty) | Takes up space, optionally as a colored block or divider |

**Provider widgets.** They read from a shared provider defined in [`providers.yaml`](../configuration/providers-yaml.md) instead of making their own requests.

| Widget | What it does |
|---|---|
| [`provider`](provider-widgets.md#provider) | Displays a value from a provider as text |
| [`providerflip`](provider-widgets.md#providerflip) | Picks a child based on provider data |
| [`providerimage`](provider-widgets.md#providerimage) | Displays an image whose URL comes from provider data |
| [`providerbarchart`](provider-widgets.md#providerbarchart) | Draws a minimal bar chart from a list of numbers |

**Push widgets.** They sit on top of another widget and show a notification when something POSTs to them over the [HTTP server](../configuration/conf-yaml.md#server).

| Widget | What it does |
|---|---|
| [`notifiabletext`](push-widgets.md#notifiabletext) | Shows a temporary text notification over its child |
| [`notifiableimage`](push-widgets.md#notifiableimage) | Shows a temporary image notification over its child |
