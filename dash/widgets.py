import datetime
import inspect
import io
import itertools
import logging
import math
import sys
import threading
import time

import pygame
import requests

from dash.fonts import FontCache

font_cache = FontCache()


_name_to_widget_map = {}


def window(seq, n=2):
    "Returns a sliding window (of width n) over data from the iterable"
    "   s -> (s0,s1,...s[n-1]), (s1,s2,...,sn), ...                   "
    it = iter(seq)
    result = tuple(itertools.islice(it, n))
    if len(result) == n:
        yield result
    for elem in it:
        result = result[1:] + (elem,)
        yield result


def map_all_the_widgets_in_here():
    for name, obj in inspect.getmembers(sys.modules[__name__]):
        if inspect.isclass(obj) and issubclass(obj, Widget):
            if 'Widget' in obj.__name__:
                class_name = obj.__name__.split('Widget')[0].lower()
                if not class_name:
                    continue
                _name_to_widget_map[class_name] = obj


def create_widget_tree(widget_dictionary):
    widget_name = widget_dictionary['widget']
    widget_parameters = {key: value for key, value in widget_dictionary.items() if key not in ['widget', 'children']}
    widget = _name_to_widget_map[widget_name](**widget_parameters)

    if 'children' in widget_dictionary:
        for child in widget_dictionary['children']:
            widget.add_widget(create_widget_tree(child))

    return widget


def stop_all_widgets(main_widget):
    if isinstance(main_widget, ContainerWidget):
        for widget in main_widget.widget_list:
            logging.debug('Going deeper in {}'.format(main_widget))
            stop_all_widgets(widget)
    elif isinstance(main_widget, UpdaterWidget):
        logging.debug('Stopping UpdaterWidget {}'.format(main_widget))
        main_widget.stop()


class Widget(object):
    def __init__(self, size=None):
        self.size = size
        self.dirty = True

    def is_dirty(self):
        return self.dirty

    def tick(self):
        pass

    def render(self, size):
        if self.size != size:
            self.size = size
            self.dirty = True


class ContainerWidget(Widget):
    def __init__(self, size=None):
        super().__init__(size)
        self.widget_list = list()

    def is_dirty(self):
        return self.dirty or any([widget.is_dirty() for widget in self.widget_list])

    def add_widget(self, widget):
        self.widget_list.append(widget)

    def tick(self):
        for widget in self.widget_list:
            widget.tick()


class ScreenWidget(ContainerWidget):
    def __init__(self, size, color=(0, 0, 0)):
        super().__init__(size)
        self.color = color

    def add_widget(self, widget):
        if self.widget_list:
            raise Exception('ScreenWidget can only have one child')
        else:
            super().add_widget(widget)

    def render(self, size):
        super().render(size)

        surface = pygame.Surface(self.size, 0, 32)
        surface.fill(self.color)

        #self.size = (self.size[0] - 1, self.size[1])

        child_surface = self.widget_list[0].render(self.size)

        surface.blit(child_surface, (0, 0))

        self.dirty = False

        return surface


class GridWidget(ContainerWidget):
    def __init__(self, rows, columns, row_ratios=None, column_ratios=None, padding=0, color=None):
        super().__init__()
        self.rows = rows
        self.columns = columns
        self.padding = padding
        self.color = color
        if row_ratios is not None:
            self.row_ratios = row_ratios
        else:
            self.row_ratios = [1] * self.rows

        if column_ratios is not None:
            self.column_ratios = column_ratios
        else:
            self.column_ratios = [1] * self.columns
        self.surface = None

    def calculate_percentage_sizes(self, length, ratios):
        percentage_ratios = [ratio / sum(ratios) for ratio in ratios]
        percentage_sizes = list(map(int, [length * percentage_ratio for percentage_ratio in percentage_ratios]))

        return percentage_sizes

    def calculate_percentage_coordinates(self, percentage_sizes):
        relative_start_coordinates = [0] + percentage_sizes[:-1]
        absolute_start_coordinates = list(itertools.accumulate(relative_start_coordinates))

        return absolute_start_coordinates

    def render(self, size):
        if size != self.size:
            self.size = size
            self.dirty = True
            self.surface = pygame.Surface(self.size, pygame.SRCALPHA, 32)

        horizontal_sizes = self.calculate_percentage_sizes(self.size[0], self.column_ratios)
        horizontal_positions = self.calculate_percentage_coordinates(horizontal_sizes)

        vertical_sizes = self.calculate_percentage_sizes(self.size[1], self.row_ratios)
        vertical_positions = self.calculate_percentage_coordinates(vertical_sizes)

        for widget, coords, widget_size in zip(
                self.widget_list,
                itertools.product(horizontal_positions, vertical_positions),
                itertools.product(horizontal_sizes, vertical_sizes)):

            if not widget.is_dirty() and not self.dirty:
                continue

            #logging.debug('{} is dirty'.format(widget))

            widget_size = list(widget_size)
            widget_size[0] -= self.padding * 2
            widget_size[1] -= self.padding * 2

            coords = list(coords)
            coords[0] += self.padding
            coords[1] += self.padding

            if self.color is not None:
                self.surface.fill(self.color, pygame.Rect(coords, widget_size))
            else:
                self.surface.fill((0, 0, 0, 0), pygame.Rect(coords, widget_size))

            self.surface.blit(widget.render(size=widget_size), coords)

        self.dirty = False

        return self.surface


class TextWidget(Widget):
    def __init__(self, font_path, text='', text_size=None, color=(0, 0, 0), padding=0, align='left', vertical_align='top'):
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
    def __init__(self):
        super().__init__()
        self.grid_widget = GridWidget(rows=2, columns=1, row_ratios=[7, 3])
        self.hour_widget = TextWidget('OpenSans-ExtraBold.ttf', color=(255, 255, 255), padding=2, align='center', vertical_align='center')
        self.date_widget = TextWidget('OpenSans-Regular.ttf', color=(255, 255, 255), padding=2, align='center')
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


class WidgetUpdaterThread(threading.Thread):
    def __init__(self, widget, frequency):
        super(WidgetUpdaterThread, self).__init__()
        self._stop_event = threading.Event()
        self.widget = widget
        self.frequency = frequency
        self.last_update = int(time.time())

        logging.debug('Initialized {}'.format(self))

    def stop(self):
        self._stop_event.set()

    def run(self):
        try:
            while not self._stop_event.is_set():
                now = int(time.time())
                if now - self.last_update >= self.frequency:
                    logging.debug('Updating {}'.format(self.widget))
                    self.widget.update()
                    self.last_update = now
                time.sleep(0.1)
        except Exception as e:
            logging.warning(str(e))


class UpdaterWidget(Widget):
    def __init__(self):
        super().__init__()
        self.update_frequency = 30
        self.update_thread = WidgetUpdaterThread(self, self.update_frequency)

        self.update()
        self.update_thread.start()

    def stop(self):
        self.update_thread.stop()
        logging.debug('{} waiting for thread to terminate'.format(self))
        self.update_thread.join()
        logging.debug('{} joined'.format(self))

    def update(self):
        pass


class RESTWidget(UpdaterWidget):
    def __init__(self, url, json_path, format_string, text_size=None, auth=None):
        self.url = url
        self.json_path = json_path
        self.format_string = format_string
        self.update_frequency = 30
        self.value = ''
        self.text_widget = TextWidget('OpenSans-ExtraBold.ttf', color=(255, 255, 255), padding=6, text_size=text_size, align='center', vertical_align='center')

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
        response_json = response.json()
        json_path_list = self.json_path.split('.')
        while json_path_list:
            response_json = response_json[json_path_list.pop(0)]

        self.value = self.format_string.format(response_json)
        logging.debug('Updated {} to {}'.format(self, self.value))

    def render(self, size):
        self.size = size

        self.text_widget.set_text(self.value)

        return self.text_widget.render(self.size)


class ImageWidget(Widget):
    def __init__(self, image_data):
        super().__init__()
        self.image_data = image_data
        self.old_surface = None
        self.dirty = True

    def set_image(self, image_data):
        if image_data != self.image_data:
            self.image_data = image_data
            self.dirty = True

    def render(self, size):
        super().render(size)

        if self.image_data is None:
            self.old_surface = pygame.Surface(self.size, pygame.SRCALPHA, 32)
        elif self.dirty:
            loaded_image_surface = pygame.image.load(io.BytesIO(self.image_data))
            original_size = loaded_image_surface.get_size()
            adjusted_sizes = list()

            for picture_axis, container_axis in zip(original_size, self.size):
                if picture_axis != container_axis:
                    ratio = picture_axis / container_axis
                    adjusted_sizes.append(tuple(int(original_axis / ratio) for original_axis in original_size))

            final_size = self.size
            for adjusted_size in adjusted_sizes:
                if adjusted_size[0] <= self.size[0] and adjusted_size[1] <= self.size[1]:
                    final_size = adjusted_size
                    break

            resized_picture = pygame.transform.smoothscale(loaded_image_surface, final_size)
            picture_position = ((self.size[0] - final_size[0]) / 2, (self.size[1] - final_size[1]) / 2)

            final_surface = pygame.Surface(self.size, pygame.SRCALPHA, 32)
            final_surface.blit(resized_picture, picture_position)
            self.old_surface = final_surface

        self.dirty = False
        return self.old_surface


class RESTImageWidget(UpdaterWidget):
    def __init__(self, url, json_path, auth=None):
        self.url = url
        self.json_path = json_path
        self.update_frequency = 30
        self.image_widget = ImageWidget(image_data=None)
        self.image_data = None

        self.requests_kwargs = {
            'headers': {}
        }
        if auth is not None:
            if 'bearer' in auth:
                self.requests_kwargs['headers']['Authorization'] = 'Bearer {}'.format(auth['bearer'])
        # This needs to happen at the end because it actually starts the update thread
        super().__init__()

    def is_dirty(self):
        return self.image_widget.is_dirty()

    def update(self):
        response = requests.get(self.url, **self.requests_kwargs)
        response_json = response.json()
        json_path_list = self.json_path.split('.')
        while json_path_list:
            response_json = response_json[json_path_list.pop(0)]

        image_url = response_json
        image_response = requests.get(image_url)
        self.image_data = image_response.content
        logging.debug('Updated {}'.format(self))

        self.dirty = True

    def render(self, size):
        self.image_widget.set_image(self.image_data)

        return self.image_widget.render(size)


class HTTPImageWidget(UpdaterWidget):
    def __init__(self, url, auth=None):
        self.url = url
        self.update_frequency = 30
        self.image_widget = ImageWidget(image_data=None)
        self.image_data = None

        self.requests_kwargs = {
            'headers': {}
        }
        if auth is not None:
            if 'bearer' in auth:
                self.requests_kwargs['headers']['Authorization'] = 'Bearer {}'.format(auth['bearer'])
        # This needs to happen at the end because it actually starts the update thread
        super().__init__()

    def update(self):
        response = requests.get(self.url, **self.requests_kwargs)
        self.image_data = response.content
        logging.debug('Updated {}'.format(self))

    def render(self, size):
        self.image_widget.set_image(self.image_data)

        return self.image_widget.render(size)


class LabelWidget(ContainerWidget):
    def __init__(self, text, position='above', text_size=None):
        super().__init__()
        self.text_widget = TextWidget(font_path='OpenSans-Regular.ttf', text=text, text_size=text_size, color=(255, 255, 255), align='center', vertical_align='top')
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


class FlipWidget(ContainerWidget):
    def __init__(self, interval=5, transition=1, ease=2):
        super().__init__()
        self.last_update = int(time.time())
        self.moving = False
        self.current_widget = 0
        self.ticker = self.last_update
        self.interval = interval
        self.transition = transition
        self.ease = ease

    def is_dirty(self):
        return self.moving or self.widget_list[self.current_widget].is_dirty()

    def ease_in_out(self, value, ease):
        return (value**ease) / ((value ** ease) + ((1 - value)**ease))

    def tick(self):
        if time.time() - self.last_update >= self.interval:
            if not self.moving:  # This allows for the current animation to complete
                self.moving = True
                self.ticker = time.time()
                self.last_update = int(time.time())

    def render(self, size):
        if self.moving:
            surface = pygame.Surface(size, pygame.SRCALPHA, 32)
            if self.transition != 0:
                transition_percentage = min(self.ease_in_out((time.time() - self.ticker) / self.transition, self.ease), 1)
            else:
                transition_percentage = 1

            current_widget = self.widget_list[self.current_widget]
            next_widget = self.widget_list[(self.current_widget + 1) % len(self.widget_list)]

            surface.blit(current_widget.render(size), (-(size[0] * transition_percentage), 0))
            surface.blit(next_widget.render(size), (size[0] * (1 - transition_percentage), 0))

            if time.time() - self.ticker >= self.transition:
                self.moving = False
                self.current_widget = (self.current_widget + 1) % len(self.widget_list)

            return surface
        else:
            return self.widget_list[self.current_widget].render(size)


map_all_the_widgets_in_here()
