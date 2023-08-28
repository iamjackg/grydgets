import itertools
import time

import pygame

from grydgets.widgets.base import ContainerWidget


class ScreenWidget(ContainerWidget):
    def __init__(self, size, color=(0, 0, 0)):
        super().__init__(size)
        self.color = color

    def add_widget(self, widget):
        if self.widget_list:
            raise Exception("ScreenWidget can only have one child")
        else:
            super().add_widget(widget)

    def render(self, size):
        super().render(size)

        surface = pygame.Surface(self.size, 0, 32)
        surface.fill(self.color)

        # self.size = (self.size[0] - 1, self.size[1])

        child_surface = self.widget_list[0].render(self.size)

        surface.blit(child_surface, (0, 0))

        self.dirty = False

        return surface


class GridWidget(ContainerWidget):
    def __init__(
        self, rows, columns, row_ratios=None, column_ratios=None, padding=0, color=None
    ):
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
        percentage_sizes = list(
            map(
                int,
                [length * percentage_ratio for percentage_ratio in percentage_ratios],
            )
        )

        return percentage_sizes

    def calculate_percentage_coordinates(self, percentage_sizes):
        relative_start_coordinates = [0] + percentage_sizes[:-1]
        absolute_start_coordinates = list(
            itertools.accumulate(relative_start_coordinates)
        )

        return absolute_start_coordinates

    def render(self, size):
        if size != self.size:
            self.size = size
            self.dirty = True
            self.surface = pygame.Surface(self.size, pygame.SRCALPHA, 32)

        horizontal_sizes = self.calculate_percentage_sizes(
            self.size[0], self.column_ratios
        )
        horizontal_positions = self.calculate_percentage_coordinates(horizontal_sizes)

        vertical_sizes = self.calculate_percentage_sizes(self.size[1], self.row_ratios)
        vertical_positions = self.calculate_percentage_coordinates(vertical_sizes)

        for widget, coords, widget_size in zip(
            self.widget_list,
            itertools.product(horizontal_positions, vertical_positions),
            itertools.product(horizontal_sizes, vertical_sizes),
        ):

            if not widget.is_dirty() and not self.dirty:
                continue

            # logging.debug('{} is dirty'.format(widget))

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

            try:
                self.surface.blit(widget.render(size=widget_size), coords)
            except TypeError:
                pass

        self.dirty = False

        return self.surface


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
        return (value ** ease) / ((value ** ease) + ((1 - value) ** ease))

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
                transition_percentage = min(
                    self.ease_in_out(
                        (time.time() - self.ticker) / self.transition, self.ease
                    ),
                    1,
                )
            else:
                transition_percentage = 1

            current_widget = self.widget_list[self.current_widget]
            next_widget = self.widget_list[
                (self.current_widget + 1) % len(self.widget_list)
            ]

            surface.blit(
                current_widget.render(size), (-(size[0] * transition_percentage), 0)
            )
            surface.blit(
                next_widget.render(size), (size[0] * (1 - transition_percentage), 0)
            )

            if time.time() - self.ticker >= self.transition:
                self.moving = False
                self.current_widget = (self.current_widget + 1) % len(self.widget_list)

            return surface
        else:
            return self.widget_list[self.current_widget].render(size)
