import datetime
import logging

import pygame
import requests

from grydgets.widgets.base import Widget, UpdaterWidget, ContainerWidget
from grydgets.widgets.containers import GridWidget
from grydgets.fonts import FontCache

font_cache = FontCache()


class TextWidget(Widget):
    def __init__(self, font_path=None, text='', text_size=None, color=(0, 0, 0), padding=0, align='left', vertical_align='top'):
        super().__init__()
        self.color = color
        self.align = align
        self.vertical_align = vertical_align
        self.font_path = font_path
        self.padding = padding
        self.text = text
        self.dirty = True
        self.surface = None
        self.text_size = text_size

    def set_text(self, text):
        if text != self.text:
            self.text = text
            self.dirty = True

    def render(self, size):
        super().render(size)
        if self.dirty:
            #logging.debug('{} I am dirty'.format(self))
            self.surface = pygame.Surface(self.size, pygame.SRCALPHA, 32)

            real_size = (self.size[0] - (self.padding * 2), self.size[1] - (self.padding * 2))

            text_size = self.text_size or real_size[1]
            text_surface = None
            while text_surface is None or text_surface.get_width() > real_size[0]:
                font = font_cache.get_font(self.font_path, text_size)
                text_surface = font.render(self.text, 1, self.color)
                text_size -= 1

            blit_coordinates = [self.padding, self.padding]
            if self.align == 'center':
                blit_coordinates[0] += (real_size[0] - text_surface.get_width()) / 2

            # self.surface.fill((255, 0, 0), pygame.Rect([self.padding, self.padding], [real_size[0], 1]))
            # self.surface.fill((255, 255, 0), pygame.Rect([self.padding, self.padding + font.get_ascent()], [real_size[0], 1]))
            # self.surface.fill((0, 255, 0), pygame.Rect([self.padding, self.padding - font.get_descent()], [real_size[0], 1]))
            # self.surface.fill((0, 255, 255), pygame.Rect([self.padding, self.padding + font.get_height()], [real_size[0], 1]))
            # self.surface.fill((0, 0, 255), pygame.Rect([self.padding, self.padding + font.get_linesize()], [real_size[0], 1]))
            # self.surface.fill((255, 0, 255), pygame.Rect([self.padding, self.padding + text_size], [real_size[0], 1]))
            # print(text_size, font.get_ascent(), font.get_descent(), font.get_height())

            blit_coordinates[1] -= (font.get_ascent() - text_size - font.get_descent())
            real_text_height = text_size + font.get_descent()
            if self.vertical_align == 'center':
                blit_coordinates[1] += (real_size[1] - real_text_height) / 2
            elif self.vertical_align == 'bottom':
                blit_coordinates[1] += (real_size[1] - real_text_height)

            self.surface.blit(text_surface, blit_coordinates)

            self.dirty = False

        return self.surface


class DateClockWidget(Widget):
    def __init__(self, time_font_path=None, date_font_path=None):
        super().__init__()
        self.grid_widget = GridWidget(rows=2, columns=1, row_ratios=[7, 3])
        self.hour_widget = TextWidget(font_path=time_font_path, color=(255, 255, 255), padding=2, align='center', vertical_align='center')
        self.date_widget = TextWidget(font_path=date_font_path, color=(255, 255, 255), padding=2, align='center')
        self.grid_widget.add_widget(self.hour_widget)
        self.grid_widget.add_widget(self.date_widget)
        self.surface = None

    def is_dirty(self):
        return self.hour_widget.is_dirty() or self.date_widget.is_dirty()

    def tick(self):
        self.hour_widget.set_text(datetime.datetime.now().strftime('%H:%M'))
        self.date_widget.set_text(datetime.datetime.now().strftime('%A, %B %d'))

    def render(self, size):
        super().render(size)

        if self.is_dirty() or self.dirty:
            self.surface = self.grid_widget.render(self.size)

        self.dirty = False
        return self.surface


class RESTWidget(UpdaterWidget):
    def __init__(self, url, json_path=None, format_string=None, font_path=None, text_size=None, auth=None):
        self.url = url
        self.json_path = json_path
        self.format_string = format_string or '{}'
        self.update_frequency = 30
        self.value = ''
        self.text_widget = TextWidget(font_path=font_path, color=(255, 255, 255), padding=6, text_size=text_size, align='center', vertical_align='center')

        self.requests_kwargs = {
            'headers': {}
        }
        if auth is not None:
            if 'bearer' in auth:
                self.requests_kwargs['headers']['Authorization'] = 'Bearer {}'.format(auth['bearer'])
        # This needs to happen at the end because it actually starts the update thread
        super().__init__()

    def is_dirty(self):
        return self.text_widget.is_dirty()

    def update(self):
        response = requests.get(self.url, **self.requests_kwargs)
        if self.json_path is not None:
            response_json = response.json()
            json_path_list = self.json_path.split('.')
            while json_path_list:
                response_json = response_json[json_path_list.pop(0)]
            text = response_json
        else:
            text = response.text

        self.value = self.format_string.format(text)
        logging.debug('Updated {} to {}'.format(self, self.value))

    def render(self, size):
        self.size = size

        self.text_widget.set_text(self.value)

        return self.text_widget.render(self.size)


class LabelWidget(ContainerWidget):
    def __init__(self, text, font_path=None, position='above', text_size=None):
        super().__init__()
        self.text_widget = TextWidget(font_path=font_path, text=text, text_size=text_size, color=(255, 255, 255), align='center', vertical_align='top')
        self.position = position

        grid_proportions = [1, 2]
        if self.position == 'below':
            grid_proportions = [2, 1]

        self.grid_widget = GridWidget(columns=1, rows=2, row_ratios=grid_proportions, padding=4)

    def is_dirty(self):
        return self.grid_widget.is_dirty()

    def add_widget(self, widget):
        super(LabelWidget, self).add_widget(widget)
        if self.position == 'above':
            self.grid_widget.add_widget(self.text_widget)
            self.grid_widget.add_widget(widget)
        elif self.position == 'below':
            self.grid_widget.add_widget(widget)
            self.grid_widget.add_widget(self.text_widget)

    def render(self, size):
        return self.grid_widget.render(size)
