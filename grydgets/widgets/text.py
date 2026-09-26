from __future__ import annotations

import datetime
import logging
from functools import lru_cache
from typing import Any, Callable

import pygame

from grydgets import rest_fetch
from grydgets.colors import ColorInput, parse_color, parse_optional_color
from grydgets.widgets.base import Widget, UpdaterWidget, ContainerWidget, renamed_parameter
from grydgets.widgets.containers import GridWidget
from grydgets.widgets.painting import paint_background
from grydgets.fonts import FontCache, scale_text_size

font_cache = FontCache()


# Letters that reach the usual descender depth.
DESCENDER_REFERENCE = "gjpqy"


@lru_cache(maxsize=64)
def descender_depth(font: pygame.font.Font) -> int:
    """How far below the baseline the font's descenders reach, in pixels.

    Measured from real glyphs, since a font's declared descent can be much
    deeper than its letters go. It's the same for every string in the font,
    so text with and without descenders is sized the same way.
    """
    glyphs = [m for m in font.metrics(DESCENDER_REFERENCE) if m is not None]
    if not glyphs:
        return -font.get_descent()
    return max(0, -min(m[2] for m in glyphs))


def fit_font(
    font_path: str | None,
    text: str,
    size: int,
    max_width: int,
    fits_height: Callable[[pygame.font.Font, int], bool] | None = None,
) -> tuple[pygame.font.Font, int]:
    """The font at ``size``, shrunk one step at a time until ``text`` fits
    ``max_width`` and, if given, ``fits_height(font, size)`` is true."""
    font = font_cache.get_font(font_path, size)
    while size > 1 and (
        font.size(text)[0] > max_width
        or (fits_height is not None and not fits_height(font, size))
    ):
        size -= 1
        font = font_cache.get_font(font_path, size)
    return font, size


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

    def _descenders_fit(self, font: pygame.font.Font, text_size: int) -> bool:
        """Whether descenders stay inside the widget at this size.

        Alignment only counts the part of the text above the baseline, so
        descenders hang below the aligned box, and may hang into the bottom
        padding. Bottom alignment puts the baseline on the bottom edge of the
        text area, so no size helps there.
        """
        available = self.size[1] - self.padding * 2
        above_baseline = text_size + font.get_descent()
        depth = descender_depth(font)
        if self.vertical_align == "center":
            return above_baseline + 2 * depth <= available + 2 * self.padding
        if self.vertical_align == "top":
            return above_baseline + depth <= available + self.padding
        return True

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

            # Only a configured cap is scaled; the cell height fallback is
            # already in this screen's pixels.
            text_size = (
                scale_text_size(self.text_size) if self.text_size else real_size[1]
            )
            font, text_size = fit_font(
                self.font_path, self.text, text_size, real_size[0], self._descenders_fit
            )
            text_surface = font.render(self.text, True, self.color)

            blit_coordinates = [self.padding, self.padding]
            if self.align == "center":
                blit_coordinates[0] += (real_size[0] - text_surface.get_width()) / 2
            elif self.align == "right":
                blit_coordinates[0] += real_size[0] - text_surface.get_width()

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
    # Each line is as big as fits in its share of the height (and the width),
    # and the two are then stacked and centred as one block.
    TIME_SHARE = 0.7
    PADDING = 2
    # The space between the two lines, as a fraction of the date's height.
    GAP = 0.4

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
        self.time_font_path = time_font_path
        self.date_font_path = date_font_path
        self.time_color = parse_optional_color(time_color, "time_color") or color
        self.date_color = parse_optional_color(date_color, "date_color") or color
        self.background_color = parse_optional_color(background_color, "background_color")
        self.corner_radius = corner_radius
        self.time_text = ""
        self.date_text = ""
        self.surface: pygame.Surface | None = None
        self.tick()

    def tick(self) -> None:
        now = datetime.datetime.now()
        time_text = now.strftime("%H:%M")
        date_text = now.strftime("%A, %B %d")
        if (time_text, date_text) != (self.time_text, self.date_text):
            self.time_text, self.date_text = time_text, date_text
            self.dirty = True

    def _ink(self, font_path: str | None, text: str, color, height: int) -> pygame.Surface:
        """``text`` as large as fits the width and ``height``, cropped to its ink."""
        font, _ = fit_font(font_path, text, height, self.size[0] - self.PADDING * 2)
        rendered = font.render(text, True, color)
        ink = rendered.get_bounding_rect()
        # Cropping only vertically keeps each line centred on its advance width,
        # which is how the text widget centres too.
        return rendered.subsurface((0, ink.top, rendered.get_width(), ink.height))

    def render(self, size: tuple[int, int]) -> pygame.Surface:
        super().render(size)

        if self.dirty or self.surface is None:
            self.surface = pygame.Surface(self.size, pygame.SRCALPHA, 32)
            paint_background(self.surface, self.background_color, self.size, self.corner_radius)

            time_height = round(self.size[1] * self.TIME_SHARE) - self.PADDING * 2
            date_height = self.size[1] - round(self.size[1] * self.TIME_SHARE) - self.PADDING * 2
            time_line = self._ink(self.time_font_path, self.time_text, self.time_color, time_height)
            date_line = self._ink(self.date_font_path, self.date_text, self.date_color, date_height)

            gap = round(date_line.get_height() * self.GAP)
            top = (self.size[1] - time_line.get_height() - gap - date_line.get_height()) / 2
            for line in (time_line, date_line):
                self.surface.blit(line, ((self.size[0] - line.get_width()) / 2, top))
                top += line.get_height() + gap

        self.dirty = False
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
