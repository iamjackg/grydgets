# Push widgets

Push widgets receive their data from POST requests made to the
`/notify` endpoint on the [HTTP server](../configuration/conf-yaml.md#server). The server is started automatically as soon as
one of them appears in `widgets.yaml`.

You *must* specify a `name` for them in order to be able to target them. 

The server binds to `127.0.0.1` by default, so if the request is coming from another machine (Home Assistant, for
example), you'll need to set `server.host` to `0.0.0.0`. If `server.control_token` is set, send it in an `Authorization: Bearer <token>`
header.

## notifiabletext

Draws a temporqary text notification instead of its child for an amount of time.

### When you'd want this

Use it for short alerts that should interrupt whatever's on screen: someone at the door, the washing machine being
done, a reminder to take the bins out. Wrap your whole dashboard in one for full-screen alerts, or just one panel
for something smaller.

### Parameters

*   `font_path`: The path to a `.ttf` file to use for the notification text.
*   `padding` _(optional)_: The gap around the notification text, in pixels. Defaults to `0`.
*   `text_size` _(optional)_: The size of the notification text in pixels.
*   `color` _(optional)_: The default colour of the notification text, see [Colors](../configuration/colors.md).
    Defaults to `[255, 255, 255]` (white).
*   `background_color` _(optional)_: The default colour behind the notification, see
    [Colors](../configuration/colors.md). If you leave it out, the text is drawn straight over the child.
*   `corner_radius` _(optional)_: The corner radius of `background_color`, in pixels. Defaults to `0`.

### Sending a notification

The POST body is a JSON object with these keys:

*   `widget`: The `name` of the widget to notify.
*   `text`: The text to show.
*   `duration` _(optional)_: How long to show it for, in seconds. Defaults to `5`.
*   `color`, `background_color` _(optional)_: Colours for this notification only. The next notification goes back to
    the colours configured on the widget. If a colour can't be parsed, it's logged and ignored.

### Example

```yaml
  - widget: notifiabletext
    name: fullscreen-notification
    font_path: 'OpenSans-ExtraBold.ttf'
    padding: 10
    text_size: 100
    children:
      - widget: grid # ... the rest of the widgets
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

## notifiableimage

Draws an image notification instead of its child for a few seconds.

### When you'd want this

Use it to show a picture that goes with an event, like a snapshot from the doorbell camera when someone rings.

### Parameters

It doesn't take any parameters other than `name` and its single child.

### Sending a notification

The POST body is a JSON object with these keys:

*   `widget`: The `name` of the widget to notify.
*   `url`: The URL of the image to show.
*   `duration` _(optional)_: How long to show it for, in seconds. Defaults to `5`.

!!! warning "Set a control token if the port isn't private"

    Grydgets fetches whatever URL is in the request, so anyone who can reach the port can put any image
    they like on your dashboard. Set a [`control_token`](../configuration/conf-yaml.md#server) to stop
    that.

### Example

You can nest notifiable widgets, so the same dashboard can get both text and image notifications:

```yaml
  - widget: notifiableimage
    name: fullscreen-notification-image
    children:
      - widget: notifiabletext
        name: fullscreen-notification
        font_path: 'OpenSans-ExtraBold.ttf'
        children:
          - widget: grid # ... main content widget
```

```bash
curl -X POST \
     -H "Content-Type: application/json" \
     -d '{"widget": "fullscreen-notification-image", "url": "https://example.com/your_image.jpg"}' \
     http://192.168.1.1:5000/notify
```
