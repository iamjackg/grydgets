import argparse
import os
import signal
import pygame
from pygame.transform import rotate
import logging
import time
import threading
from flask import Flask, request, jsonify

from grydgets import config
from grydgets.outputs import create_outputs
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
        "--config-dir",
        default=None,
        metavar="DIR",
        help="Directory containing config files, fonts, and images (default: current directory)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.config_dir is not None:
        os.chdir(args.config_dir)

    def load_widget_tree():
        return config.load_yaml(args.widgets)

    widget_tree = load_widget_tree()
    conf = config.load_config("conf.yaml")
    conf = config.migrate_config(conf)

    render_config = conf["graphics"]
    screen_size = tuple(render_config["resolution"])
    image_module.smooth_scaling = render_config.get("smooth-scaling", True)

    logging.getLogger().setLevel(logging.getLevelName(conf["logging"]["level"].upper()))

    # Create outputs
    outputs = create_outputs(conf["outputs"], render_config)
    any_needs_display = any(o.needs_display for o in outputs)
    fps_limit = max(o.preferred_fps for o in outputs)

    # Set SDL environment variables before pygame.init()
    if not any_needs_display:
        os.environ["SDL_VIDEODRIVER"] = "dummy"

    for output in outputs:
        output.pre_init()

    stop_everything = threading.Event()
    reload_lock = threading.RLock()

    pygame.init()
    pygame.mixer.quit()

    # Setup outputs (creates display surface if needed)
    for output in outputs:
        output.setup(screen_size)

    # Initialize and start providers
    provider_manager = ProviderManager('providers.yaml')
    provider_manager.start_all()

    widget_manager = WidgetManager(provider_manager)

    screen_widget = ScreenWidget(
        screen_size,
        image_path=widget_tree.get("background_image", None),
        color=widget_tree.get("background_color", (0, 0, 0)),
        drop_shadow=widget_tree.get("drop_shadow", False),
    )

    screen_widget.add_widget(widget_manager.create_widget_tree(widget_tree["widgets"][0]))

    # Flask app for notifications
    app = Flask(__name__)

    @app.route("/notify", methods=["POST"])
    def widget():
        payload = request.get_json()
        requested_widget = payload["widget"]
        if requested_widget not in widget_manager.name_to_instance:
            return jsonify({"success": False, "error": "Widget not found"}), 400

        widget_manager.name_to_instance[requested_widget].notify(payload)
        return jsonify({"success": True})

    def run_server():
        app.run(host="0.0.0.0", port=conf["server"]["port"])

    server_thread = threading.Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()

    def reload_configuration(signum, frame):
        nonlocal screen_widget, widget_tree, provider_manager, widget_manager, conf
        nonlocal outputs, fps_limit, any_needs_display, last_surface
        logging.info("Reloading configuration...")
        with reload_lock:
            try:
                new_conf = config.load_config("conf.yaml")
                new_conf = config.migrate_config(new_conf)

                # Check if display requirements changed (requires restart)
                new_outputs = create_outputs(new_conf["outputs"], new_conf["graphics"])
                new_needs_display = any(o.needs_display for o in new_outputs)
                if new_needs_display != any_needs_display:
                    logging.warning(
                        "Display mode changed. This requires a restart. "
                        "Ignoring configuration reload."
                    )
                    return

                # Stop old outputs
                for output in outputs:
                    output.stop()

                # Setup new outputs
                outputs = new_outputs
                for output in outputs:
                    output.setup(screen_size)
                fps_limit = max(o.preferred_fps for o in outputs)
                any_needs_display = new_needs_display
                last_surface = None

                new_widget_tree = load_widget_tree()
                logging.info("Stopping all widgets...")
                widget_manager.stop_all_widgets(screen_widget)

                logging.info("Stopping all providers...")
                provider_manager.stop_all()

                logging.info("Starting new providers...")
                provider_manager = ProviderManager('providers.yaml')
                provider_manager.start_all()

                widget_manager = WidgetManager(provider_manager)

                screen_widget = ScreenWidget(
                    screen_size,
                    image_path=new_widget_tree.get("background_image", None),
                    color=new_widget_tree.get("background_color", (0, 0, 0)),
                    drop_shadow=new_widget_tree.get("drop_shadow", False),
                )
                screen_widget.add_widget(widget_manager.create_widget_tree(new_widget_tree["widgets"][0]))
                widget_tree = new_widget_tree
                conf = new_conf
                logging.info("Configuration reloaded successfully.")
            except Exception as e:
                logging.error(f"Failed to reload configuration: {e}")

    signal.signal(signal.SIGUSR1, reload_configuration)

    fps_time = time.time()
    frame_data = list()
    last_surface = None
    while not stop_everything.is_set():
        frame_start = time.time()
        try:
            if any_needs_display:
                for event in pygame.event.get():
                    if event.type in [pygame.QUIT, pygame.MOUSEBUTTONDOWN]:
                        stop_everything.set()

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
