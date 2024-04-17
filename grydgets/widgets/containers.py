import itertools
import time

import pygame

from grydgets.benchmark import benchmark
from grydgets.widgets.base import ContainerWidget


def load_and_scale_image(image_path, size):
    # Load the image
    image = pygame.image.load(image_path)

    # Get image dimensions
    image_width, image_height = image.get_size()

    # Determine scale factor to fit the image to the longest side of the surface
    scale_factor = max(size[0] / image_width, size[1] / image_height)

    # Calculate new image dimensions
    new_dimensions = (int(image_width * scale_factor), int(image_height * scale_factor))

    # Resize the image
    scaled_image = pygame.transform.scale(image, new_dimensions)

    return scaled_image


class ScreenWidget(ContainerWidget):
    def __init__(self, size, color=(0, 0, 0), image_path=None, drop_shadow=False, **kwargs):
        super().__init__(size, **kwargs)
        self.color = color
        self.size = size
        self.image_path = image_path
        self.image = None
        self.drop_shadow = drop_shadow
        if image_path is not None:
            self.image = load_and_scale_image(image_path, size)

    def add_widget(self, widget):
        if self.widget_list:
            raise Exception("ScreenWidget can only have one child")
        else:
            super().add_widget(widget)

    @benchmark
    def render(self, size):
        super().render(size)

        if self.size != size and self.image_path is not None:
            self.image = load_and_scale_image(self.image_path, size)

        surface = pygame.Surface(self.size, pygame.SRCALPHA, 32)
        if self.image is not None:
            surface.blit(self.image, (0, 0))
        else:
            surface.fill(self.color)

        # self.size = (self.size[0] - 1, self.size[1])

        child_surface = self.widget_list[0].render(self.size)

        if self.drop_shadow:
            mask = pygame.mask.from_surface(child_surface, threshold=200)
            mask_surface = mask.to_surface(setcolor=(0, 0, 0, 255), unsetcolor=(0, 0, 0, 0))
            white_mask_surface = mask.to_surface(
                setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0)
            )
            blurred_mask_surface = pygame.transform.box_blur(mask_surface, radius=5)
            blurred_mask_surface.blit(
                white_mask_surface,
                (0, 0),
                special_flags=pygame.BLEND_RGBA_SUB,
            )

            surface.blit(blurred_mask_surface, (0, 0))
        surface.blit(child_surface, (0, 0))

        self.dirty = False

        return surface


class GridWidget(ContainerWidget):
    def __init__(
        self,
        rows,
        columns,
        row_ratios=None,
        column_ratios=None,
        padding=0,
        color=None,
        widget_color=None,
        corner_radius=0,
        widget_corner_radius=0,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.rows = rows
        self.columns = columns
        self.padding = padding
        self.color = color
        self.widget_color = widget_color
        self.corner_radius = corner_radius
        self.widget_corner_radius = widget_corner_radius
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

    @benchmark
    def render(self, size):
        if size != self.size:
            self.size = size
            self.dirty = True
            self.surface = pygame.Surface(self.size, pygame.SRCALPHA, 32)

        if not (self.is_dirty() or self.dirty):
            return self.surface

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

            final_widget_surface = pygame.Surface(widget_size, pygame.SRCALPHA, 32)
            # final_widget_surface.fill((0, 0, 0, 0))
            if self.widget_color is not None:
                if self.widget_corner_radius != 0:
                    pygame.draw.rect(
                        final_widget_surface,
                        self.widget_color,
                        pygame.Rect((0, 0), widget_size),
                        border_radius=self.widget_corner_radius,
                        # border_radius=widget_size[1] // 4,
                    )
                    # print(widget_size)
                else:
                    final_widget_surface.fill(
                        self.widget_color, pygame.Rect((0, 0), widget_size)
                    )

                final_widget_surface = (
                    final_widget_surface.convert_alpha().premul_alpha()
                )

            try:
                widget_surf = widget.render(size=widget_size)
                final_widget_surface.blit(
                    widget_surf,
                    (0, 0),
                    # special_flags=pygame.BLEND_PREMULTIPLIED,
                )
                self.surface.fill((0, 0, 0, 0), pygame.Rect(coords, widget_size))
                # self.surface = self.surface.premul_alpha()
                self.surface.blit(
                    final_widget_surface,
                    coords,
                    # special_flags=pygame.BLEND_PREMULTIPLIED,
                )
            except TypeError:
                pass
            # self.surface.fill((0, 0, 0, 0), pygame.Rect(coords, widget_size))
            # self.surface.blit(
            #     widget.render(widget_size).premul_alpha(),
            #     coords,
            #     special_flags=pygame.BLEND_PREMULTIPLIED,
            # )

        self.dirty = False

        if self.corner_radius:
            mask_surface = pygame.Surface(self.size, pygame.SRCALPHA)
            mask_surface.fill((0, 0, 0, 0))
            pygame.draw.rect(
                mask_surface,
                (255, 255, 255, 255),
                pygame.Rect((0, 0), self.size),
                border_radius=self.corner_radius,
                # border_radius=self.size[1] // 4,
            )
            self.surface.blit(mask_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)

        return self.surface


class FlipWidget(ContainerWidget):
    def __init__(self, interval=5, transition=1, ease=2, **kwargs):
        super().__init__(**kwargs)
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
        return (value**ease) / ((value**ease) + ((1 - value) ** ease))

    def tick(self):
        if time.time() - self.last_update >= self.interval:
            if not self.moving:  # This allows for the current animation to complete
                self.moving = True
                self.ticker = time.time()
                self.last_update = int(time.time())

        if self.moving:
            for widget in self.widget_list:
                widget.tick()
        else:
            self.widget_list[self.current_widget].tick()

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
