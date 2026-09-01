import argparse
import functools
import hmac
import ipaddress
import json
import os
import queue
import signal
import sys
from datetime import datetime, timezone
import pygame
from pygame.transform import rotate
import logging
import time
import threading
from flask import Flask, request, jsonify

from grydgets import appearance, config, fonts, theme
from grydgets.outputs import create_outputs
from grydgets.outputs.stream import SHUTDOWN, StreamOutput
from grydgets.widgets import image as image_module
from grydgets.widgets.containers import ScreenWidget
from grydgets.widgets.widgets import WidgetManager
from grydgets.providers import ProviderManager

logging.basicConfig(
    format="[%(asctime)s] %(levelname)s:%(name)s:%(message)s", level=logging.DEBUG
)


def parse_args():
    parser = argparse.ArgumentParser(description="Grydgets dashboard")
    parser.add_argument(
        "--widgets",
        default="widgets.yaml",
        metavar="FILE",
        help="Widget configuration file (default: widgets.yaml)",
    )
    parser.add_argument(
        "--theme",
        default=None,
        metavar="FILE",
        help="Theme file replacing the widgets file's theme block "
        "(default: use the theme in the widgets file)",
    )
    parser.add_argument(
        "--config-dir",
        default=None,
        metavar="DIR",
        help="Directory containing config files, fonts, and images (default: current directory)",
    )
    return parser.parse_args()


def fail(error, config_dir):
    """Report a bad config file and stop.

    A config error isn't a bug in grydgets, so it exits with a message rather
    than a traceback. ``config_dir`` is the directory relative paths were
    resolved against, or None if the process never moved.
    """
    message = f"grydgets: {error}"
    if config_dir is not None:
        message += f"\ngrydgets: config paths are relative to {config_dir}"
    sys.exit(message)


def apply_text_scale(render_config):
    """Hand ``graphics.text-scale`` to the font layer."""
    scale = render_config.get("text-scale", 1.0)
    fonts.set_text_scale(scale)
    if scale != 1.0:
        logging.info("Configured text sizes are multiplied by %g", scale)


# How often the sun is asked whether it's still the same time of day.
# Sunrise/sunset shift by seconds a day, so checking more often finds nothing.
MODE_CHECK_INTERVAL = 30

# How often /events sends a comment line, so a router that drops idle
# connections silently turns into a read timeout instead of a stuck client.
SSE_PING_INTERVAL = 20


def is_loopback(host):
    """Whether only this machine can reach an address.

    Hostnames other than "localhost" are not resolved. A name pointing at
    127.0.0.1 is rare enough not to justify a DNS lookup at startup, and
    getting it wrong only costs one unprinted warning.
    """
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


# Displays name their own resolution on /frame. The ceiling is only here so a
# typo cannot ask the render host to scale a frame up to something enormous.
MAX_FRAME_DIMENSION = 7680


class BadSize(Exception):
    """A caller asked for a frame size that cannot be served."""


def requested_size(args):
    """The size a display asked its frame to be encoded at, or None.

    None means "as rendered", which is what a caller that names no size gets.
    """
    if "width" not in args and "height" not in args:
        return None
    try:
        size = (int(args["width"]), int(args["height"]))
    except (KeyError, ValueError):
        raise BadSize("width and height must both be given, as integers")
    if not all(1 <= side <= MAX_FRAME_DIMENSION for side in size):
        raise BadSize(f"width and height must be between 1 and {MAX_FRAME_DIMENSION}")
    return size


def etag_matches(header, etag):
    """Whether an If-None-Match header names ``etag``."""
    if not header or etag is None:
        return False
    return f'"{etag}"' in [token.strip() for token in header.split(",")]


def main():
    args = parse_args()

    config_dir = None
    if args.config_dir is not None:
        try:
            os.chdir(args.config_dir)
        except OSError as e:
            sys.exit(f"grydgets: --config-dir {args.config_dir}: {e.strerror}")
        # Read back rather than joining: every config path from here on is
        # relative to this, and it's what error messages have to quote.
        config_dir = os.getcwd()

    def load_widget_trees(theme_files):
        """Every widget tree that might be shown, keyed by the mode that shows it.

        Read on every call, not once, so SIGUSR1 picks up an edited theme file
        the same way it picks up an edited widgets file.

        Both themes are loaded up front so that a theme file missing an entry
        the base theme defines (``theme.check_replacement``) is reported at
        startup rather than at sunset.
        """
        if theme_files is None:
            return {
                None: config.load_widget_config(args.widgets, theme_file=args.theme)
            }
        return {
            mode: config.load_widget_config(args.widgets, theme_file=path)
            for mode, path in theme_files.items()
        }

    try:
        conf = config.load_config("conf.yaml")
    except (config.ConfigError, theme.ThemeError) as e:
        fail(e, config_dir)
    conf = config.migrate_config(conf)

    # --theme names one theme for the whole run, so it turns day/night
    # switching off rather than fighting with it.
    appearance_conf = conf.get("appearance")
    if appearance_conf is not None and args.theme is not None:
        logging.info(
            "--theme %s was given, so conf.yaml's day/night themes are not used",
            args.theme,
        )
        appearance_conf = None

    # schedule is None while theme_files isn't when the block names two
    # themes but no coordinates, so only POST /theme moves between them.
    schedule = None
    theme_files = None
    default_mode = appearance.DAY
    try:
        if appearance_conf is not None:
            schedule = appearance.SunSchedule.from_config(appearance_conf)
            theme_files = appearance_conf["themes"]
            default_mode = appearance_conf.get("default", appearance.DAY)
        widget_trees = load_widget_trees(theme_files)
    except (config.ConfigError, theme.ThemeError, appearance.AppearanceError) as e:
        fail(e, config_dir)

    # None when there is a single theme; "day"/"night" when there are two.
    active_mode = None
    # Set by the /theme endpoint to hold one theme regardless of the sun, and
    # the instant that hold lapses -- None meaning it doesn't.
    forced_mode = None
    forced_until = None
    if theme_files is not None:
        active_mode = default_mode
        if schedule is None:
            # Two themes and no coordinates: only POST /theme can switch them,
            # and only if http_control turned that endpoint on.
            if appearance_conf.get("http_control", False):
                logging.info(
                    "Day and night themes, but no coordinates: starting on the "
                    "%s theme, which changes only when POST /theme says so",
                    active_mode,
                )
            else:
                logging.warning(
                    "Day and night themes, but no coordinates and "
                    "appearance.http_control is off: the %s theme will never "
                    "change. Give a latitude and longitude to switch by the "
                    "sun, or set http_control: true to switch over HTTP",
                    active_mode,
                )
        else:
            logging.info(schedule.describe())
            by_sun = schedule.mode_at()
            if by_sun is None:
                logging.warning(
                    "The sun neither rises nor sets at this location today, so "
                    "the %s theme is being used until it does",
                    active_mode,
                )
            else:
                active_mode = by_sun

    render_config = conf["graphics"]
    screen_size = tuple(render_config["resolution"])
    image_module.smooth_scaling = render_config.get("smooth-scaling", True)
    apply_text_scale(render_config)

    logging.getLogger().setLevel(logging.getLevelName(conf["logging"]["level"].upper()))

    outputs = create_outputs(conf["outputs"], render_config)
    any_needs_display = any(o.needs_display for o in outputs)
    fps_limit = max(o.preferred_fps for o in outputs)

    # SDL_VIDEODRIVER only takes effect if set before pygame.init() runs.
    if not any_needs_display:
        os.environ["SDL_VIDEODRIVER"] = "dummy"

    for output in outputs:
        output.pre_init()

    stop_everything = threading.Event()
    reload_lock = threading.RLock()

    pygame.init()
    pygame.mixer.quit()

    for output in outputs:
        output.setup(screen_size)

    try:
        provider_manager = ProviderManager('providers.yaml')
    except (config.ConfigError, theme.ThemeError) as e:
        fail(e, config_dir)
    provider_manager.start_all()

    def build_for_mode(mode):
        """A manager and screen for one mode's widget tree, built against
        whichever providers are running now. Doesn't touch what's on screen --
        the caller swaps it in and stops the old one."""
        tree = widget_trees[mode]
        manager = WidgetManager(provider_manager)
        screen = ScreenWidget(
            screen_size,
            image_path=tree.get("background_image", None),
            background_color=tree.get("background_color", (0, 0, 0)),
            drop_shadow=tree.get("drop_shadow", False),
        )
        screen.add_widget(manager.create_widget_tree(tree["widgets"][0]))
        return manager, screen

    widget_manager, screen_widget = build_for_mode(active_mode)

    def switch_mode(mode):
        """Change theme by rebuilding the widget tree, leaving the providers
        running.

        None of the data changes when the look does, so tearing the providers
        down the way a full reload does would only mean every provider-backed
        widget waits on a fetch it doesn't need. Keeping them means the new
        tree paints from the values already cached, and only widgets that do
        their own HTTP (the ``rest`` ones) go and ask again.
        """
        nonlocal widget_manager, screen_widget, active_mode, last_surface
        new_manager, new_screen = build_for_mode(mode)
        # Built before the old one is stopped: if construction raises, the
        # dashboard on screen is still whole and still ticking.
        widget_manager.stop_all_widgets(screen_widget)
        widget_manager, screen_widget = new_manager, new_screen
        active_mode = mode
        last_surface = None

    def active_stream_output():
        """The stream output in the live outputs list, or None.

        Looked up per request rather than captured, because a reload replaces
        every output instance and can add or remove this one.
        """
        for output in outputs:
            if isinstance(output, StreamOutput):
                return output
        return None

    def http_control_enabled():
        """Whether appearance.http_control is on. Read from the live config so
        a reload that changes it takes effect on the next request.

        --theme does not turn this off. With one theme in force, /theme answers
        400 and says so, which is more useful than the 404 that means the
        endpoint is disabled.
        """
        return bool((conf.get("appearance") or {}).get("http_control", False))

    def server_reasons():
        """What currently needs the HTTP server. Empty means nothing does.

        The ``server:`` block configures a server but never asks for one. Each
        of these is checked live, because a reload can change the answer.
        """
        reasons = []
        if active_stream_output() is not None:
            reasons.append("a stream output")
        if widget_manager.name_to_instance:
            reasons.append("notifiable widgets")
        if http_control_enabled():
            reasons.append("appearance.http_control")
        return reasons

    def feature_off(what):
        """404 for an endpoint whose feature is off.

        Every route is registered unconditionally, because Flask routes cannot
        be unregistered and a reload can turn any of these features on or off.
        Availability is therefore a per-request answer, not a per-route one.
        """
        return jsonify({"success": False, "error": what}), 404

    def require_token(scope):
        """Bearer-token check for one scope. Does nothing if that token is unset.

        The two scopes are independent so the read path can be closed without
        editing the Home Assistant automations that already POST to /notify.
        """
        def decorator(handler):
            @functools.wraps(handler)
            def wrapper(*args, **kwargs):
                expected = config.server_settings(conf)["auth"].get(f"{scope}_token")
                if expected is not None:
                    supplied = request.headers.get("Authorization", "")
                    prefix = "Bearer "
                    if not supplied.startswith(prefix) or not hmac.compare_digest(
                        supplied[len(prefix):], expected
                    ):
                        return jsonify({
                            "success": False,
                            "error": f"a valid {scope} bearer token is required",
                        }), 401
                return handler(*args, **kwargs)
            return wrapper
        return decorator

    app = Flask(__name__)

    @app.route("/notify", methods=["POST"])
    @require_token("control")
    def widget():
        if not widget_manager.name_to_instance:
            return feature_off(
                "no widget in the current theme's tree can be notified"
            )
        payload = request.get_json()
        requested_widget = payload["widget"]
        if requested_widget not in widget_manager.name_to_instance:
            return jsonify({"success": False, "error": "Widget not found"}), 400

        widget_manager.name_to_instance[requested_widget].notify(payload)
        return jsonify({"success": True})

    @app.route("/frame", methods=["GET"])
    @require_token("stream")
    def frame():
        """The latest published frame, or 304 if the caller already has it.

        ``?width=&height=`` asks for it at the caller's own resolution, so a
        display never scales what it receives.
        """
        output = active_stream_output()
        if output is None:
            return feature_off("no stream output is configured")
        try:
            size = requested_size(request.args)
        except BadSize as e:
            return jsonify({"success": False, "error": str(e)}), 400
        # Ask for the tag before the bytes: a display that is already showing
        # this frame is answered without anything being encoded for it.
        etag, published_at = output.current_etag(size)
        if etag is None:
            return jsonify({
                "success": False,
                "error": "no frame has been published yet",
            }), 503
        if etag_matches(request.headers.get("If-None-Match"), etag):
            response = app.response_class(status=304)
        else:
            data, etag, published_at = output.current_frame(size)
            response = app.response_class(data, mimetype=output.content_type)
        response.headers["ETag"] = f'"{etag}"'
        response.headers["Cache-Control"] = "no-store"
        # Wall-clock time the server published this frame, so clients can
        # measure how long it took to notice, download, and display it.
        response.headers["X-Frame-Published-At"] = f"{published_at:.6f}"
        return response

    @app.route("/events", methods=["GET"])
    @require_token("stream")
    def events():
        """An event per published frame, so clients don't have to poll."""
        output = active_stream_output()
        if output is None:
            return feature_off("no stream output is configured")
        # Displays send their size here too. Nothing is served from it -- the
        # size that matters is the one on /frame -- but it is the only place
        # the log can say what is connected and how big it is.
        try:
            size = requested_size(request.args)
        except BadSize as e:
            return jsonify({"success": False, "error": str(e)}), 400
        logging.info(
            "Display at %s connected%s",
            request.remote_addr,
            "" if size is None else f", showing {size[0]}x{size[1]}",
        )

        def generate(output):
            # Capture the output instead of looking it up per event. A reload
            # replaces it, and the old one pushes SHUTDOWN into this queue so
            # the client reconnects to the new one.
            subscriber = output.subscribe()
            try:
                # The etag here only says which frame is current. Displays
                # compare the one from /frame, which names a size as well.
                etag, published_at = output.current_etag()
                if etag is not None:
                    yield f"data: {json.dumps({'etag': etag, 'published_at': published_at})}\n\n"
                while True:
                    try:
                        item = subscriber.get(timeout=SSE_PING_INTERVAL)
                    except queue.Empty:
                        yield ": ping\n\n"
                        continue
                    if item is SHUTDOWN:
                        return
                    etag, published_at = item
                    yield f"data: {json.dumps({'etag': etag, 'published_at': published_at})}\n\n"
            finally:
                output.unsubscribe(subscriber)

        return app.response_class(
            generate(output),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-store",
                # Stops nginx buffering, which would hold every event until
                # the connection closed.
                "X-Accel-Buffering": "no",
            },
        )

    def no_switching():
        return jsonify({
            "success": False,
            "error": "there is only one theme: conf.yaml has no "
                     "'appearance' block, or --theme was given",
        }), 400

    def following_sun():
        """Whether the sun is what decides right now. False whenever there is
        no schedule at all, since then nothing is being followed."""
        return schedule is not None and forced_mode is None

    @app.route("/theme", methods=["GET"])
    @require_token("control")
    def get_theme():
        """Which theme is up, what decides it, and when it changes next --
        without changing anything."""
        if not http_control_enabled():
            return feature_off("appearance.http_control is off")
        if theme_files is None:
            return no_switching()
        upcoming = schedule.next_change() if schedule is not None else None
        return jsonify({
            "success": True,
            "mode": active_mode,
            "following_sun": following_sun(),
            "held_until": forced_until.isoformat() if forced_until else None,
            "next_change": upcoming[0].isoformat() if upcoming else None,
            "next_mode": upcoming[1] if upcoming else None,
        })

    @app.route("/theme", methods=["POST"])
    @require_token("control")
    def set_theme():
        """Hold one theme, or hand control back to the sun.

        With coordinates configured this is for looking at both themes without
        waiting for dusk, and for overriding the sun when something else knows
        better. Without them it is the only thing that changes the theme, so
        whatever is doing the deciding -- an automation, a light sensor, a
        button -- posts here.
        """
        nonlocal forced_mode, forced_until
        if not http_control_enabled():
            return feature_off("appearance.http_control is off")
        if theme_files is None:
            return no_switching()

        payload = request.get_json(silent=True) or {}
        requested = payload.get("mode")
        if requested not in appearance.MODES + ("auto",):
            return jsonify({
                "success": False,
                "error": "'mode' must be one of: day, night, auto",
            }), 400
        if requested == "auto" and schedule is None:
            return jsonify({
                "success": False,
                "error": "'auto' means follow the sun, which needs a latitude "
                         "and longitude in conf.yaml's appearance block",
            }), 400
        hold = payload.get("hold", "next")
        if hold not in ("next", "forever"):
            return jsonify({
                "success": False,
                "error": "'hold' must be 'next' (until the sun's next turn) "
                         "or 'forever'",
            }), 400

        with reload_lock:
            if requested == "auto":
                forced_mode, forced_until = None, None
            else:
                forced_mode = requested
                # Holds lapse at the next boundary by default, so a one-off
                # request doesn't silently stop the dashboard following the sun.
                upcoming = schedule.next_change() if schedule is not None else None
                forced_until = upcoming[0] if (hold == "next" and upcoming) else None
            wanted = forced_mode or schedule.mode_at() or active_mode
            if wanted != active_mode:
                switch_mode(wanted)
            return jsonify({
                "success": True,
                "mode": active_mode,
                "following_sun": following_sun(),
                "held_until": forced_until.isoformat() if forced_until else None,
            })

    def start_server():
        """Start the HTTP server if something needs it, and log either way.

        It cannot be started or stopped later. Werkzeug's server has no clean
        in-process shutdown, and a socket appearing on SIGUSR1 would be a
        surprise. A reload that changes the answer logs a warning instead.
        """
        reasons = server_reasons()
        settings = config.server_settings(conf)
        if not reasons:
            logging.info(
                "Not starting the HTTP server: nothing here needs one (no "
                "stream output, no notifiable widgets, "
                "appearance.http_control off)"
            )
            return False

        logging.info(
            "HTTP server on %s:%s, for %s",
            settings["host"], settings["port"], ", ".join(reasons),
        )
        remote_facing = [r for r in reasons if r != "appearance.http_control"]
        if remote_facing and is_loopback(settings["host"]):
            logging.warning(
                "The HTTP server is bound to %s, so nothing off this machine "
                "can reach it -- and %s only matter to something that can. "
                "Set server.host to 0.0.0.0 or this machine's LAN address "
                "unless whatever calls it runs here too",
                settings["host"], " and ".join(remote_facing),
            )

        def run_server():
            # Threaded: each open /events connection holds a thread for as
            # long as the client keeps it.
            app.run(host=settings["host"], port=settings["port"], threaded=True)

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        return True

    server_running = start_server()
    bound_host = config.server_settings(conf)["host"]
    bound_port = config.server_settings(conf)["port"]

    def reload_configuration(signum, frame):
        nonlocal screen_widget, provider_manager, widget_manager, conf
        nonlocal outputs, fps_limit, any_needs_display, last_surface
        nonlocal schedule, widget_trees, active_mode, theme_files, default_mode
        logging.info("Reloading configuration...")
        with reload_lock:
            try:
                new_conf = config.load_config("conf.yaml")
                new_conf = config.migrate_config(new_conf)

                new_outputs = create_outputs(new_conf["outputs"], new_conf["graphics"])
                new_needs_display = any(o.needs_display for o in new_outputs)
                if new_needs_display != any_needs_display:
                    logging.warning(
                        "Display mode changed. This requires a restart. "
                        "Ignoring configuration reload."
                    )
                    return

                # Read at render time, so the tree rebuilt below picks up a
                # changed scale without anything being reset on the widgets.
                apply_text_scale(new_conf["graphics"])

                for output in outputs:
                    output.stop()

                outputs = new_outputs
                for output in outputs:
                    output.setup(screen_size)
                fps_limit = max(o.preferred_fps for o in outputs)
                any_needs_display = new_needs_display
                last_surface = None

                # Everything is loaded before anything is swapped in, so a bad
                # edit leaves the running dashboard as it was.
                new_appearance = new_conf.get("appearance")
                if new_appearance is not None and args.theme is not None:
                    new_appearance = None
                new_schedule = (
                    appearance.SunSchedule.from_config(new_appearance)
                    if new_appearance is not None
                    else None
                )
                new_theme_files = (
                    new_appearance["themes"] if new_appearance is not None else None
                )
                new_trees = load_widget_trees(new_theme_files)

                logging.info("Stopping all widgets...")
                widget_manager.stop_all_widgets(screen_widget)

                logging.info("Stopping all providers...")
                provider_manager.stop_all()

                logging.info("Starting new providers...")
                provider_manager = ProviderManager('providers.yaml')
                provider_manager.start_all()

                schedule = new_schedule
                theme_files = new_theme_files
                widget_trees = new_trees
                if new_appearance is not None:
                    default_mode = new_appearance.get("default", appearance.DAY)

                # Whichever theme was up stays up, so a reload doesn't put the
                # day theme on a dark screen at midnight. A mode that no longer
                # exists falls back to what the sun says now.
                if active_mode not in widget_trees:
                    active_mode = None
                    if theme_files is not None:
                        active_mode = forced_mode or default_mode
                        if schedule is not None:
                            active_mode = forced_mode or schedule.mode_at() or default_mode
                            logging.info(schedule.describe())

                widget_manager, screen_widget = build_for_mode(active_mode)
                conf = new_conf
                warn_about_server_changes()
                logging.info("Configuration reloaded successfully.")
            except Exception as e:
                logging.error(f"Failed to reload configuration: {e}")

    def warn_about_server_changes():
        """Warn when a reload asked for an HTTP server it cannot get.

        The rest of the reload still applies; the endpoints follow the new
        configuration on the next request. Only the socket is fixed for the
        life of the process.
        """
        reasons = server_reasons()
        if bool(reasons) != server_running:
            if reasons:
                logging.warning(
                    "The configuration now wants an HTTP server (%s), but "
                    "starting one requires a restart. Nothing is listening",
                    ", ".join(reasons),
                )
            else:
                logging.warning(
                    "Nothing needs the HTTP server any more, but stopping it "
                    "requires a restart. The port stays open"
                )
        elif server_running:
            settings = config.server_settings(conf)
            if (settings["host"], settings["port"]) != (bound_host, bound_port):
                logging.warning(
                    "server.host/server.port changed to %s:%s, but moving the "
                    "socket requires a restart. Still listening on %s:%s",
                    settings["host"], settings["port"], bound_host, bound_port,
                )

    signal.signal(signal.SIGUSR1, reload_configuration)

    fps_time = time.time()
    frame_data = list()
    last_surface = None
    next_mode_check = 0.0
    while not stop_everything.is_set():
        frame_start = time.time()
        try:
            if any_needs_display:
                for event in pygame.event.get():
                    if event.type in [pygame.QUIT, pygame.MOUSEBUTTONDOWN]:
                        stop_everything.set()

            if schedule is not None and frame_start >= next_mode_check:
                next_mode_check = frame_start + MODE_CHECK_INTERVAL

                if forced_until is not None and datetime.now(timezone.utc) >= forced_until:
                    logging.info(
                        "The %s theme was held until the sun's next turn, "
                        "which has come: following the sun again",
                        forced_mode,
                    )
                    forced_mode, forced_until = None, None

                # None means the sun didn't rise or set today, which is not a
                # reason to change anything: whatever is up stays up.
                wanted = None if forced_mode is not None else schedule.mode_at()
                if wanted is not None and wanted != active_mode:
                    with reload_lock:
                        logging.info("Switching to the %s theme", wanted)
                        try:
                            switch_mode(wanted)
                            logging.info(schedule.describe())
                        except Exception as e:
                            logging.error(f"Failed to switch to the {wanted} theme: {e}")

            with reload_lock:
                screen_widget.tick()

                ready_outputs = [o for o in outputs if o.wants_update()]
                is_dirty = screen_widget.is_dirty()

                if ready_outputs and (is_dirty or last_surface is None):
                    if render_config.get("flip", False):
                        last_surface = rotate(screen_widget.render(screen_size), 180)
                    else:
                        last_surface = screen_widget.render(screen_size)
                    freshly_rendered = True
                else:
                    freshly_rendered = False

                if last_surface is not None:
                    ready_set = set(id(o) for o in ready_outputs)
                    for output in outputs:
                        if id(output) in ready_set:
                            output.on_frame(last_surface, freshly_rendered or output._pending_dirty)
                            output._pending_dirty = False
                        elif freshly_rendered:
                            output._pending_dirty = True

            sleep_time = max((1 / fps_limit) - (time.time() - frame_start), 0)
            time.sleep(sleep_time)
        except KeyboardInterrupt:
            stop_everything.set()

        frame_end = time.time()
        frame_data.append(frame_end - frame_start)
        if time.time() - fps_time > 0.5:
            logging.debug("FPS: {}".format(1 / (sum(frame_data) / len(frame_data))))
            fps_time = time.time()
            frame_data = list()

    for output in outputs:
        output.stop()
    widget_manager.stop_all_widgets(screen_widget)
    provider_manager.stop_all()
    pygame.quit()
