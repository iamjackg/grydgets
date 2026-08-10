from __future__ import annotations

import datetime
import logging
from typing import Any

import pygame

from grydgets import rest_fetch
from grydgets.colors import ColorInput, parse_color, parse_optional_color
from grydgets.widgets.base import Widget, UpdaterWidget, ContainerWidget, renamed_parameter
from grydgets.widgets.containers import GridWidget
from grydgets.widgets.painting import paint_background
from grydgets.fonts import FontCache, scale_text_size

font_cache = FontCache()


class TextWidget(Widget):
    def __init__(
        self,
        font_path: str | None = None,
        text: str = "",
        text_size: int | None = None,
        color: ColorInput = (255, 255, 255),
        background_color: ColorInput | None = None,
        corner_radius: int = 0,
        padding: int = 0,
        align: str = "left",
        vertical_align: str = "top",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.color = parse_color(color, "color")
        self.background_color = parse_optional_color(
            background_color, "background_color"
        )
        self.corner_radius = corner_radius
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

    def set_color(self, color: ColorInput) -> None:
        parsed = parse_color(color, "color")
        if parsed != self.color:
            self.color = parsed
            self.dirty = True

    def set_background_color(self, background_color: ColorInput | None) -> None:
        parsed = parse_optional_color(background_color, "background_color")
        if parsed != self.background_color:
            self.background_color = parsed
            self.dirty = True

    def render(self, size: tuple[int, int]) -> pygame.Surface:
        super().render(size)
        if self.dirty:
            self.surface = pygame.Surface(self.size, pygame.SRCALPHA, 32)
            # The backdrop covers the whole widget; padding only insets the
            # text, so a padded label still gets a full-bleed panel.
            paint_background(
                self.surface, self.background_color, self.size, self.corner_radius
            )

            real_size = (
                self.size[0] - (self.padding * 2),
                self.size[1] - (self.padding * 2),
            )

            # A cap that was written down is in the pixels of whichever screen
            # it was written for, so graphics.text-scale converts it. Falling
            # back to the cell height needs no conversion: the cell is already
            # this screen's size.
            text_size = (
                scale_text_size(self.text_size) if self.text_size else real_size[1]
            )
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
        color: ColorInput = (255, 255, 255),
        time_color: ColorInput | None = None,
        date_color: ColorInput | None = None,
        background_color: ColorInput | None = None,
        corner_radius: int = 0,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        color = parse_color(color, "color")
        time_color = parse_optional_color(time_color, "time_color") or color
        date_color = parse_optional_color(date_color, "date_color") or color
        self.grid_widget = GridWidget(
            rows=2,
            columns=1,
            row_ratios=[7, 3],
            widget_background_color=parse_optional_color(
                background_color, "background_color"
            ),
            corner_radius=corner_radius,
            **kwargs
        )
        self.hour_widget = TextWidget(
            font_path=time_font_path,
            color=time_color,
            padding=2,
            align="center",
            vertical_align="center",
            **kwargs
        )
        self.date_widget = TextWidget(
            font_path=date_font_path,
            color=date_color,
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
        color: ColorInput = (255, 255, 255),
        background_color: ColorInput | None = None,
        corner_radius: int = 0,
        auth: dict[str, Any] | None = None,
        method: str | None = None,
        payload: dict[str, Any] | None = None,
        padding: int = 6,
        align: str = "center",
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
            color=color,
            background_color=background_color,
            corner_radius=corner_radius,
            padding=padding,
            text_size=text_size,
            align=align,
            vertical_align=vertical_align,
            **kwargs
        )

        self.auth = auth
        # This needs to happen at the end because it actually starts the update thread
        super().__init__(**kwargs)

    def is_dirty(self) -> bool:
        return self.text_widget.is_dirty()

    def update(self) -> None:
        result = rest_fetch.fetch_text(
            self.url,
            method=self.method,
            payload=self.payload,
            auth=self.auth,
            json_path=self.json_path,
            jq_expression=self.jq_expression,
            format_string=self.format_string,
        )
        if result.connection_error is not None:
            self.logger.warning("Could not update: {}".format(result.connection_error))
        if result.extraction_error is not None:
            self.logger.error(result.extraction_error)

        if result.value != self.value:
            self.value = result.value
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
        color: ColorInput | None = None,
        text_color: ColorInput | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        color = renamed_parameter(self.logger, "color", color, "text_color", text_color)
        self.text_widget = TextWidget(
            font_path=font_path,
            text=text,
            text_size=text_size,
            color=parse_color(color if color is not None else (255, 255, 255), "color"),
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
