import datetime
import logging

import pygame

from grydgets.widgets.base import Widget, UpdaterWidget, ContainerWidget
from grydgets.widgets.containers import GridWidget
from grydgets.fonts import FontCache
from grydgets.json_utils import extract_json_path

font_cache = FontCache()


class TextWidget(Widget):
    def __init__(
        self,
        font_path=None,
        text="",
        text_size=None,
        color=(255, 255, 255),
        padding=0,
        align="left",
        vertical_align="top",
        **kwargs
    ):
        super().__init__(**kwargs)
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

    def set_color(self, color):
        if color != self.color:
            self.color = color
            self.dirty = True

    def render(self, size):
        super().render(size)
        if self.dirty:
            # self.logger.debug('I am dirty')
            self.surface = pygame.Surface(self.size, pygame.SRCALPHA, 32)

            real_size = (
                self.size[0] - (self.padding * 2),
                self.size[1] - (self.padding * 2),
            )

            text_size = self.text_size or real_size[1]
            text_surface = None
            font = None
            while text_surface is None or text_surface.get_width() > real_size[0]:
                font = font_cache.get_font(self.font_path, text_size)
                text_surface = font.render(self.text, 1, self.color)
                text_size -= 1

            shadow_text = font.render(self.text, 1, (0, 0, 0))
            shadow_surface = pygame.Surface(
                (shadow_text.get_width() + 20, shadow_text.get_height() + 20),
                pygame.SRCALPHA,
                32,
            )
            shadow_surface.blit(shadow_text, (10, 10))

            blit_coordinates = [self.padding, self.padding]
            if self.align == "center":
                blit_coordinates[0] += (real_size[0] - text_surface.get_width()) / 2

            # self.surface.fill((255, 0, 0), pygame.Rect([self.padding, self.padding], [real_size[0], 1]))
            # self.surface.fill((255, 255, 0), pygame.Rect([self.padding, self.padding + font.get_ascent()], [real_size[0], 1]))
            # self.surface.fill((0, 255, 0), pygame.Rect([self.padding, self.padding - font.get_descent()], [real_size[0], 1]))
            # self.surface.fill((0, 255, 255), pygame.Rect([self.padding, self.padding + font.get_height()], [real_size[0], 1]))
            # self.surface.fill((0, 0, 255), pygame.Rect([self.padding, self.padding + font.get_linesize()], [real_size[0], 1]))
            # self.surface.fill((255, 0, 255), pygame.Rect([self.padding, self.padding + text_size], [real_size[0], 1]))
            # print(text_size, font.get_ascent(), font.get_descent(), font.get_height())

            blit_coordinates[1] -= font.get_ascent() - text_size - font.get_descent()
            real_text_height = text_size + font.get_descent()
            if self.vertical_align == "center":
                blit_coordinates[1] += (real_size[1] - real_text_height) / 2
            elif self.vertical_align == "bottom":
                blit_coordinates[1] += real_size[1] - real_text_height

            self.surface.blit(
                pygame.transform.gaussian_blur(shadow_surface, radius=10),
                (blit_coordinates[0] - 10, blit_coordinates[1] - 10),
            )
            self.surface.blit(text_surface, blit_coordinates)

            self.dirty = False

        return self.surface


class DateClockWidget(Widget):
    def __init__(
        self, time_font_path=None, date_font_path=None, color=(255, 255, 255), **kwargs
    ):
        super().__init__(**kwargs)
        self.grid_widget = GridWidget(rows=2, columns=1, row_ratios=[7, 3], **kwargs)
        self.hour_widget = TextWidget(
            font_path=time_font_path,
            color=color,
            padding=2,
            align="center",
            vertical_align="center",
            **kwargs
        )
        self.date_widget = TextWidget(
            font_path=date_font_path, color=color, padding=2, align="center", **kwargs
        )
        self.grid_widget.add_widget(self.hour_widget)
        self.grid_widget.add_widget(self.date_widget)
        self.surface = None

    def is_dirty(self):
        return self.hour_widget.is_dirty() or self.date_widget.is_dirty()

    def tick(self):
        self.hour_widget.set_text(datetime.datetime.now().strftime("%H:%M"))
        self.date_widget.set_text(datetime.datetime.now().strftime("%A, %B %d"))

    def render(self, size):
        super().render(size)

        if self.is_dirty() or self.dirty:
            self.surface = self.grid_widget.render(self.size)

        self.dirty = False
        return self.surface


import requests
import xml.etree.ElementTree as ET


class NextbusWidget(UpdaterWidget):
    def __init__(
        self,
        agency,
        stop_id,
        route=None,
        number=1,
        font_path=None,
        text_size=None,
        **kwargs
    ):
        self.agency = agency
        self.stop_id = stop_id
        self.number = number
        self.prediction_url = "http://webservices.nextbus.com/service/publicXMLFeed?a={}&command=predictions&stopId={}".format(
            self.agency, self.stop_id
        )
        if route:
            self.prediction_url += "&r={}".format(route)
        self.value = ""

        self.text_widget = TextWidget(
            font_path=font_path,
            color=(255, 255, 255),
            padding=6,
            text_size=text_size,
            align="center",
            vertical_align="center",
            **kwargs
        )

        super().__init__(**kwargs)  # starts the update thread

    def is_dirty(self):
        return self.text_widget.is_dirty()

    def get_next_time(self):
        try:
            response = requests.get(self.prediction_url)
            if response.status_code != 200:
                text = "Error {}".format(response.status_code)
            else:
                root = ET.fromstring(response.text)
                upcoming = []
                for route in root:
                    routeNumber = route.attrib["routeTag"]
                    for direction in route:
                        for prediction in direction:
                            upcoming.append(
                                (routeNumber, int(prediction.attrib["minutes"]))
                            )

                upcoming.sort(key=lambda x: x[1])
                print(", ".join([b[1].__str__() + "m" for b in upcoming]))
                # text = f"{upcoming[0][1]} min"
                limit = min(self.number, len(upcoming))
                text = " ".join(["{}min".format(b[1]) for b in upcoming[0:limit]])
        except requests.ConnectionError as e:
            self.logger.warning("Could not update: {}".format(e))
            text = "Unavailable"
        return text

    def update(self):
        new_value = self.get_next_time()
        if new_value != self.value:
            self.value = new_value
            self.text_widget.set_text(self.value)
        self.logger.debug("Updated to {}".format(self.value))

    def render(self, size):
        self.size = size
        self.text_widget.set_text(self.get_next_time())
        return self.text_widget.render(self.size)


class RESTWidget(UpdaterWidget):
    def __init__(
        self,
        url,
        json_path=None,
        format_string=None,
        font_path=None,
        text_size=None,
        auth=None,
        method=None,
        payload=None,
        vertical_align="center",
        **kwargs
    ):
        self.url = url
        self.json_path = json_path
        self.format_string = format_string or "{}"
        self.update_frequency = 30
        self.value = ""
        self.vertical_align = vertical_align
        self.method = method or "GET"
        self.payload = payload
        self.text_widget = TextWidget(
            font_path=font_path,
            color=(255, 255, 255),
            padding=6,
            text_size=text_size,
            align="center",
            vertical_align=vertical_align,
            **kwargs
        )

        self.requests_kwargs = {"headers": {}}
        if auth is not None:
            if "bearer" in auth:
                self.requests_kwargs["headers"]["Authorization"] = "Bearer {}".format(
                    auth["bearer"]
                )
        if self.method == "POST" and self.payload:
            self.requests_kwargs["json"] = self.payload
        # This needs to happen at the end because it actually starts the update thread
        super().__init__(**kwargs)

    def is_dirty(self):
        return self.text_widget.is_dirty()

    def update(self):
        try:
            response = requests.request(
                method=self.method, url=self.url, **self.requests_kwargs
            )
            if response.status_code != 200:
                text = "Error {}".format(response.status_code)
            elif self.json_path is not None:
                response_json = response.json()
                try:
                    text = extract_json_path(response_json, self.json_path)
                except Exception as e:
                    self.logger.error(e)
                    text = "--"
            else:
                text = response.text
        except requests.ConnectionError as e:
            self.logger.warning("Could not update: {}".format(e))
            text = "Unavailable"

        if self.format_string.format(text) != self.value:
            self.value = self.format_string.format(text)
            self.text_widget.set_text(self.value)

        self.logger.debug("Updated to {}".format(self.value))

    def render(self, size):
        self.size = size

        self.text_widget.set_text(self.value)

        return self.text_widget.render(self.size)


class LabelWidget(ContainerWidget):
    def __init__(
        self,
        text,
        font_path=None,
        position="above",
        text_size=None,
        text_color=(255, 255, 255),
        **kwargs
    ):
        super().__init__(**kwargs)
        self.text_widget = TextWidget(
            font_path=font_path,
            text=text,
            text_size=text_size,
            color=text_color,
            align="center",
            vertical_align="top" if position == "below" else "center",
            **kwargs
        )
        self.position = position

        grid_proportions = [1, 2]
        if self.position == "below":
            grid_proportions = [2, 1]

        self.grid_widget = GridWidget(
            columns=1,
            rows=2,
            row_ratios=grid_proportions,
            padding=0,
        )

    def is_dirty(self):
        return self.grid_widget.is_dirty()

    def add_widget(self, widget):
        super(LabelWidget, self).add_widget(widget)
        if self.position == "above":
            self.grid_widget.add_widget(self.text_widget)
            self.grid_widget.add_widget(widget)
        elif self.position == "below":
            self.grid_widget.add_widget(widget)
            self.grid_widget.add_widget(self.text_widget)

    def render(self, size):
        return self.grid_widget.render(size)
