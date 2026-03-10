from __future__ import annotations

from typing import Any

import pygame

from grydgets.fonts import FontCache
from grydgets.json_utils import extract_data
from grydgets.providers.base import DataProvider
from grydgets.widgets.base import Widget

font_cache = FontCache()


class ProviderBarChartWidget(Widget):
    def __init__(
        self,
        providers: dict[str, DataProvider],
        data_path: str | None = None,
        jq_expression: str | None = None,
        bar_color: tuple[int, ...] = (100, 149, 237),
        bar_gap: int = 2,
        max_value: float | None = None,
        min_value: float = 0,
        midline: bool = False,
        midline_thickness: int = 1,
        midline_color: tuple[int, ...] = (255, 255, 255),
        quartline: bool = False,
        quartline_thickness: int = 1,
        quartline_color: tuple[int, ...] = (255, 255, 255),
        labels_jq_expression: str | None = None,
        labels_data_path: str | None = None,
        label_font_path: str | None = None,
        label_size: int = 12,
        label_color: tuple[int, ...] = (200, 200, 200),
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)

        if not providers or len(providers) != 1:
            raise ValueError("ProviderBarChartWidget requires exactly one provider")

        self.providers = providers
        self.provider = list(providers.values())[0]
        self.data_path = data_path
        self.jq_expression = jq_expression
        self.bar_color = tuple(bar_color)
        self.bar_gap = bar_gap
        self.max_value = max_value
        self.min_value = min_value
        self.midline = midline
        self.midline_thickness = midline_thickness
        self.midline_color = tuple(midline_color)
        self.quartline = quartline
        self.quartline_thickness = quartline_thickness
        self.quartline_color = tuple(quartline_color)
        self.labels_jq_expression = labels_jq_expression
        self.labels_data_path = labels_data_path
        self.label_font_path = label_font_path
        self.label_size = label_size
        self.label_color = tuple(label_color)

        self.last_seen_timestamp: float = 0
        self.surface: pygame.Surface | None = None

    def is_dirty(self) -> bool:
        if self.provider.get_timestamp() > self.last_seen_timestamp:
            return True
        return self.dirty

    def _extract_values(self, data: Any) -> list[float]:
        if self.data_path or self.jq_expression:
            result = extract_data(
                data,
                json_path=self.data_path,
                jq_expression=self.jq_expression,
            )
        else:
            result = data

        if not isinstance(result, list):
            result = [result]
        return [float(v) for v in result]

    def _extract_labels(self, data: Any) -> list[str] | None:
        if not self.labels_jq_expression and not self.labels_data_path:
            return None
        result = extract_data(
            data,
            json_path=self.labels_data_path,
            jq_expression=self.labels_jq_expression,
        )
        if not isinstance(result, list):
            result = [result]
        return [str(v) for v in result]

    def render(self, size: tuple[int, int]) -> pygame.Surface:
        super().render(size)  # updates self.size, may set self.dirty if size changed

        needs_redraw = self.dirty or self.provider.get_timestamp() > self.last_seen_timestamp

        if not needs_redraw and self.surface is not None:
            self.dirty = False
            return self.surface

        self.last_seen_timestamp = self.provider.get_timestamp()

        error = self.provider.get_error()
        data = self.provider.get_data()

        if error or data is None:
            if self.surface is None:
                self.surface = pygame.Surface(size, pygame.SRCALPHA, 32)
            self.dirty = False
            return self.surface

        try:
            values = self._extract_values(data)
            labels = self._extract_labels(data)
        except (KeyError, IndexError, ValueError, TypeError, StopIteration) as e:
            self.logger.debug(f"Failed to extract chart data: {e}")
            if self.surface is None:
                self.surface = pygame.Surface(size, pygame.SRCALPHA, 32)
            self.dirty = False
            return self.surface

        if not values:
            self.surface = pygame.Surface(size, pygame.SRCALPHA, 32)
            self.dirty = False
            return self.surface

        self.surface = pygame.Surface(size, pygame.SRCALPHA, 32)

        has_labels = labels is not None and len(labels) > 0
        if has_labels:
            font = font_cache.get_font(self.label_font_path, self.label_size)
            label_height = font.get_height() + 2
        else:
            font = None
            label_height = 0

        chart_height = size[1] - label_height
        chart_width = size[0]
        n = len(values)

        max_val = self.max_value if self.max_value is not None else max(values)
        min_val = self.min_value
        val_range = max_val - min_val
        if val_range <= 0:
            val_range = 1

        total_gap = self.bar_gap * (n - 1) if n > 1 else 0
        bar_width = max(1, (chart_width - total_gap) / n)

        if self.quartline:
            for quart_y in (
                chart_height // 4 - self.quartline_thickness // 2,
                chart_height * 3 // 4 - self.quartline_thickness // 2,
            ):
                pygame.draw.rect(
                    self.surface,
                    self.quartline_color,
                    pygame.Rect(0, quart_y, chart_width, self.quartline_thickness),
                )

        if self.midline:
            mid_y = chart_height // 2 - self.midline_thickness // 2
            pygame.draw.rect(
                self.surface,
                self.midline_color,
                pygame.Rect(0, mid_y, chart_width, self.midline_thickness),
            )

        for i, value in enumerate(values):
            clamped = max(min_val, min(value, max_val))
            bar_height = max(0, int(((clamped - min_val) / val_range) * chart_height))

            x = int(i * (bar_width + self.bar_gap))
            y = chart_height - bar_height
            w = max(1, int(bar_width))

            if bar_height > 0:
                pygame.draw.rect(
                    self.surface, self.bar_color, pygame.Rect(x, y, w, bar_height)
                )

            if has_labels and font is not None and labels is not None and i < len(labels):
                label_surface = font.render(labels[i], True, self.label_color)
                label_x = x + (w - label_surface.get_width()) // 2
                label_y = chart_height + 2
                self.surface.blit(label_surface, (label_x, label_y))

        self.dirty = False
        return self.surface
