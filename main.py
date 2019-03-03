import os

import pygame
import logging
import time
import threading

from grydgets import widgets, config


logging.basicConfig(level=logging.DEBUG)

widget_tree = config.load_yaml('widgets.yaml')
conf = config.load_config('conf.yaml')

if 'fb-device' in conf['graphics']:
    os.environ["SDL_FBDEV"] = '/dev/fb1'

if 'x-display' in conf['graphics']:
    os.environ["DISPLAY"] = ':0'

fps_limit = conf['graphics']['fps-limit']

pygame_flags = 0
pygame_flags |= pygame.DOUBLEBUF

if conf['graphics']['fullscreen']:
    pygame_flags |= pygame.FULLSCREEN
    pygame_flags |= pygame.HWSURFACE

logging.getLogger().setLevel(logging.getLevelName(conf['logging']['level'].upper()))

stop_everything = threading.Event()

pygame.init()
pygame.mixer.quit()

pygame.mouse.set_visible(0)

screen_size = tuple(conf['graphics']['resolution'])
screen = pygame.display.set_mode(screen_size, pygame_flags)
pygame.display.set_caption('Grydgets dashboard', 'Grydgets')

screen_widget = widgets.ScreenWidget(screen_size)

screen_widget.add_widget(widgets.create_widget_tree(widget_tree['widgets'][0]))

fps_limit = 60
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
        sleep_time = max((1 / fps_limit) - (time.time() - frame_start), 0)
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
