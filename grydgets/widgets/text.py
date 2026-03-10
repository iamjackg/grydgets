from __future__ import annotations

import base64
import datetime
import logging
from typing import Any

import pygame
import requests

from grydgets.widgets.base import Widget, UpdaterWidget, ContainerWidget
from grydgets.widgets.containers import GridWidget
from grydgets.fonts import FontCache
from grydgets.json_utils import extract_data

font_cache = FontCache()


class TextWidget(Widget):
    def __init__(
        self,
        font_path: str | None = None,
        text: str = "",
        text_size: int | None = None,
        color: tuple[int, ...] = (255, 255, 255),
        padding: int = 0,
        align: str = "left",
        vertical_align: str = "top",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.color = color
        self.align = align
        self.vertical_align = vertical_align
        self.font_path = font_path
        self.padding = padding
        self.text = text
        self.dirty = True
        self.surface: pygame.Surface | None = None
        self.text_size = text_size

    def set_text(self, text: str) -> None:
        if text != self.text:
            self.text = text
            self.dirty = True

    def set_color(self, color: tuple[int, ...]) -> None:
        if color != self.color:
            self.color = color
            self.dirty = True

    def render(self, size: tuple[int, int]) -> pygame.Surface:
        super().render(size)
        if self.dirty:
            self.surface = pygame.Surface(self.size, pygame.SRCALPHA, 32)

            real_size = (
                self.size[0] - (self.padding * 2),
                self.size[1] - (self.padding * 2),
            )

            text_size = self.text_size or real_size[1]
            font = font_cache.get_font(self.font_path, text_size)
            while font.size(self.text)[0] > real_size[0] and text_size > 1:
                text_size -= 1
                font = font_cache.get_font(self.font_path, text_size)
            text_surface = font.render(self.text, True, self.color)

            blit_coordinates = [self.padding, self.padding]
            if self.align == "center":
                blit_coordinates[0] += (real_size[0] - text_surface.get_width()) / 2

            blit_coordinates[1] -= font.get_ascent() - text_size - font.get_descent()
            real_text_height = text_size + font.get_descent()
            if self.vertical_align == "center":
                blit_coordinates[1] += (real_size[1] - real_text_height) / 2
            elif self.vertical_align == "bottom":
                blit_coordinates[1] += real_size[1] - real_text_height

            self.surface.blit(text_surface, blit_coordinates)

            self.dirty = False

        assert self.surface is not None
        return self.surface


class DateClockWidget(Widget):
    def __init__(
        self,
        time_font_path: str | None = None,
        date_font_path: str | None = None,
        color: tuple[int, ...] = (255, 255, 255),
        background_color: tuple[int, ...] | None = None,
        corner_radius: int = 0,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.grid_widget = GridWidget(
            rows=2,
            columns=1,
            row_ratios=[7, 3],
            widget_color=background_color,
            corner_radius=corner_radius,
            **kwargs
        )
        self.hour_widget = TextWidget(
            font_path=time_font_path,
            color=color,
            padding=2,
            align="center",
            vertical_align="center",
            **kwargs
        )
        self.date_widget = TextWidget(
            font_path=date_font_path,
            color=color,
            padding=2,
            align="center",
            vertical_align="top",
            **kwargs
        )
        self.grid_widget.add_widget(self.hour_widget)
        self.grid_widget.add_widget(self.date_widget)
        self.surface: pygame.Surface | None = None

    def is_dirty(self) -> bool:
        return self.hour_widget.is_dirty() or self.date_widget.is_dirty()

    def tick(self) -> None:
        self.hour_widget.set_text(datetime.datetime.now().strftime("%H:%M"))
        self.date_widget.set_text(datetime.datetime.now().strftime("%A, %B %d"))

    def render(self, size: tuple[int, int]) -> pygame.Surface:
        super().render(size)

        if self.is_dirty() or self.dirty:
            self.surface = self.grid_widget.render(self.size)

        self.dirty = False
        assert self.surface is not None
        return self.surface


class RESTWidget(UpdaterWidget):
    def __init__(
        self,
        url: str,
        json_path: str | None = None,
        jq_expression: str | None = None,
        format_string: str | None = None,
        font_path: str | None = None,
        text_size: int | None = None,
        auth: dict[str, Any] | None = None,
        method: str | None = None,
        payload: dict[str, Any] | None = None,
        vertical_align: str = "center",
        **kwargs: Any,
    ) -> None:
        self.url = url
        self.json_path = json_path
        self.jq_expression = jq_expression
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

        self.requests_kwargs: dict[str, Any] = {"headers": {}}
        if auth is not None:
            if "bearer" in auth:
                self.requests_kwargs["headers"]["Authorization"] = "Bearer {}".format(
                    auth["bearer"]
                )
            elif "basic" in auth:
                username = auth["basic"].get("username", "")
                password = auth["basic"].get("password", "")
                auth_string = f"{username}:{password}"
                encoded_auth = base64.b64encode(auth_string.encode()).decode()
                self.requests_kwargs["headers"]["Authorization"] = f"Basic {encoded_auth}"
        if self.method == "POST" and self.payload:
            self.requests_kwargs["json"] = self.payload
        # This needs to happen at the end because it actually starts the update thread
        super().__init__(**kwargs)

    def is_dirty(self) -> bool:
        return self.text_widget.is_dirty()

    def update(self) -> None:
        try:
            response = requests.request(
                method=self.method, url=self.url, **self.requests_kwargs
            )
            if response.status_code != 200:
                text = "Error {}".format(response.status_code)
            elif self.json_path is not None or self.jq_expression is not None:
                response_json = response.json()
                try:
                    text = extract_data(
                        response_json,
                        json_path=self.json_path,
                        jq_expression=self.jq_expression
                    )
                except Exception as e:
                    self.logger.error(e)
                    text = "--"
            else:
                text = response.text
        except requests.ConnectionError as e:
            self.logger.warning("Could not update: {}".format(e))
            text = "Unavailable"

        formatted_value = self.format_string.format(text)
        if formatted_value != self.value:
            self.value = formatted_value
            self.text_widget.set_text(self.value)

            self.logger.debug("Updated to {}".format(self.value))

    def render(self, size: tuple[int, int]) -> pygame.Surface:
        self.size = size

        self.text_widget.set_text(self.value)

        return self.text_widget.render(self.size)


class LabelWidget(ContainerWidget):
    def __init__(
        self,
        text: str,
        font_path: str | None = None,
        position: str = "above",
        text_size: int | None = None,
        text_color: tuple[int, ...] = (255, 255, 255),
        **kwargs: Any,
    ) -> None:
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

    def is_dirty(self) -> bool:
        return self.grid_widget.is_dirty()

    def add_widget(self, widget: Widget) -> None:
        super(LabelWidget, self).add_widget(widget)
        if self.position == "above":
            self.grid_widget.add_widget(self.text_widget)
            self.grid_widget.add_widget(widget)
        elif self.position == "below":
            self.grid_widget.add_widget(widget)
            self.grid_widget.add_widget(self.text_widget)

    def render(self, size: tuple[int, int]) -> pygame.Surface:
        return self.grid_widget.render(size)
