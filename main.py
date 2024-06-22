import os
import signal
import pygame
from pygame.transform import rotate
import logging
import time
import threading
from flask import Flask, request, jsonify

from grydgets import config
from grydgets.widgets.containers import ScreenWidget
from grydgets.widgets.widgets import WidgetManager

logging.basicConfig(
    format="[%(asctime)s] %(levelname)s:%(name)s:%(message)s", level=logging.DEBUG
)


def load_widget_tree():
    return config.load_yaml("widgets.yaml")


widget_tree = load_widget_tree()
conf = config.load_config("conf.yaml")

if "fb-device" in conf["graphics"]:
    os.environ["SDL_FBDEV"] = conf["graphics"]["fb-device"]

if "x-display" in conf["graphics"]:
    os.environ["DISPLAY"] = conf["graphics"]["x-display"]

fps_limit = conf["graphics"]["fps-limit"]

pygame_flags = 0
pygame_flags |= pygame.DOUBLEBUF

if conf["graphics"]["fullscreen"]:
    pygame_flags |= pygame.FULLSCREEN
    pygame_flags |= pygame.HWSURFACE

logging.getLogger().setLevel(logging.getLevelName(conf["logging"]["level"].upper()))

stop_everything = threading.Event()
reload_lock = threading.Lock()

pygame.init()
pygame.mixer.quit()

pygame.mouse.set_visible(0)

screen_size = tuple(conf["graphics"]["resolution"])
screen = pygame.display.set_mode(screen_size, pygame_flags)
pygame.display.set_caption("Grydgets dashboard", "Grydgets")

widget_manager = WidgetManager()

screen_widget = ScreenWidget(
    screen_size,
    image_path=widget_tree.get("background_image", None),
    color=widget_tree.get("background_color", (0, 0, 0)),
    drop_shadow=widget_tree.get("drop_shadow", False),
)

screen_widget.add_widget(widget_manager.create_widget_tree(widget_tree["widgets"][0]))

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
    global screen_widget, widget_tree
    logging.info("Reloading configuration...")
    with reload_lock:
        try:
            new_widget_tree = load_widget_tree()
            logging.info("Stopping all widgets...")
            widget_manager.stop_all_widgets(screen_widget)
            screen_widget = ScreenWidget(
                screen_size,
                image_path=new_widget_tree.get("background_image", None),
                color=new_widget_tree.get("background_color", (0, 0, 0)),
                drop_shadow=new_widget_tree.get("drop_shadow", False),
            )
            screen_widget.add_widget(widget_manager.create_widget_tree(new_widget_tree["widgets"][0]))
            widget_tree = new_widget_tree
            logging.info("Configuration reloaded successfully.")
        except Exception as e:
            logging.error(f"Failed to reload configuration: {e}")


signal.signal(signal.SIGUSR1, reload_configuration)

fps_time = time.time()
frame_data = list()
last_screen_surface = None
while not stop_everything.is_set():
    frame_start = time.time()
    try:
        for event in pygame.event.get():
            if event.type in [pygame.QUIT, pygame.MOUSEBUTTONDOWN]:
                stop_everything.set()

        with reload_lock:
            screen_widget.tick()
            if not last_screen_surface or screen_widget.is_dirty():
                if conf["graphics"].get("flip", False):
                    last_screen_surface = rotate(screen_widget.render(screen_size), 180)
                else:
                    last_screen_surface = screen_widget.render(screen_size)

                screen.blit(last_screen_surface, (0, 0))

                pygame.display.flip()

        sleep_time = max((1 / fps_limit) - (time.time() - frame_start), 0)
        # if sleep_time == 0:
        #     logging.debug('Losing frames {}'.format(sleep_time))
        time.sleep(sleep_time)
    except KeyboardInterrupt:
        stop_everything.set()

    frame_end = time.time()
    frame_data.append(frame_end - frame_start)
    if time.time() - fps_time > 0.5:
        logging.debug("FPS: {}".format(1 / (sum(frame_data) / len(frame_data))))
        fps_time = time.time()
        frame_data = list()

widget_manager.stop_all_widgets(screen_widget)
pygame.quit()
