import os

import pygame
from pygame.transform import rotate
import logging
import time
import threading
from flask import Flask, request, jsonify

from grydgets import config
from grydgets.widgets.containers import ScreenWidget
from grydgets.widgets.widgets import (
    create_widget_tree,
    stop_all_widgets,
    name_to_instance,
)

logging.basicConfig(
    format="[%(asctime)s] %(levelname)s:%(name)s:%(message)s", level=logging.DEBUG
)

widget_tree = config.load_yaml("widgets.yaml")
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

pygame.init()
pygame.mixer.quit()

pygame.mouse.set_visible(0)

screen_size = tuple(conf["graphics"]["resolution"])
screen = pygame.display.set_mode(screen_size, pygame_flags)
pygame.display.set_caption("Grydgets dashboard", "Grydgets")

screen_widget = ScreenWidget(
    screen_size,
    image_path=widget_tree.get("background_image", None),
    color=widget_tree.get("background_color", (0, 0, 0)),
)

screen_widget.add_widget(create_widget_tree(widget_tree["widgets"][0]))

app = Flask(__name__)


@app.route("/notify", methods=["POST"])
def widget():
    payload = request.get_json()
    requested_widget = payload["widget"]
    if requested_widget not in name_to_instance:
        return jsonify({"success": False, "error": "Widget not found"}), 400

    name_to_instance[requested_widget].notify(payload)
    return jsonify({"success": True})


def run_server():
    app.run(host="0.0.0.0", port=conf["server"]["port"])


server_thread = threading.Thread(target=run_server)
server_thread.daemon = True
server_thread.start()

fps_time = time.time()
frame_data = list()
while not stop_everything.is_set():
    frame_start = time.time()
    try:
        for event in pygame.event.get():
            if event.type in [pygame.QUIT, pygame.MOUSEBUTTONDOWN]:
                stop_everything.set()

        screen_widget.tick()
        if conf["graphics"].get("flip", False):
            blit_image = rotate(screen_widget.render(screen_size), 180)
        else:
            blit_image = screen_widget.render(screen_size)

        screen.blit(blit_image, (0, 0))

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
        # logging.debug("FPS: {}".format(1 / (sum(frame_data) / len(frame_data))))
        fps_time = time.time()
        frame_data = list()

stop_all_widgets(screen_widget)
pygame.quit()
