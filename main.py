import json
import os

import pygame
import logging
import time
import threading

from dash import widgets, config


logging.basicConfig(level=logging.DEBUG)

conf = config.parse_conf('widgets.yaml')

MAX_FPS = 60

flags = 0
flags |= pygame.DOUBLEBUF
if os.uname()[1] == 'raspberrypi':
    os.environ["SDL_FBDEV"] = '/dev/fb1'
    os.environ["DISPLAY"] = ':0'
    MAX_FPS = 10
    flags |= pygame.FULLSCREEN
    flags |= pygame.HWSURFACE
    logging.getLogger().setLevel(logging.INFO)

stop_everything = threading.Event()

pygame.init()
pygame.mixer.quit()

pygame.mouse.set_visible(0)

screen_size = (480, 320)
screen = pygame.display.set_mode(screen_size, flags)

screen_widget = widgets.ScreenWidget(screen_size)

screen_widget.add_widget(widgets.create_widget_tree(conf['widgets'][0]))

fps_time = time.time()
frame_data = list()
while not stop_everything.is_set():
    frame_start = time.time()
    try:
        for event in pygame.event.get():
            if event.type in [pygame.QUIT, pygame.MOUSEBUTTONDOWN]:
                stop_everything.set()

        screen_widget.tick()
        screen.blit(screen_widget.render(screen_size), (0, 0))

        pygame.display.flip()
        sleep_time = max((1/MAX_FPS) - (time.time()-frame_start), 0)
        # if sleep_time == 0:
        #     logging.debug('Losing frames {}'.format(sleep_time))
        time.sleep(sleep_time)
    except KeyboardInterrupt:
        stop_everything.set()

    frame_end = time.time()
    frame_data.append(frame_end - frame_start)
    if time.time() - fps_time > 0.5:
        logging.debug('FPS: {}'.format(1 / (sum(frame_data) / len(frame_data))))
        fps_time = time.time()
        frame_data = list()

widgets.stop_all_widgets(screen_widget)
pygame.quit()
