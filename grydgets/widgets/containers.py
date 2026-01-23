import base64
import itertools
import logging
import time
from datetime import datetime, time as datetime_time
from functools import lru_cache

import pygame
import requests

from grydgets.benchmark import benchmark
from grydgets.json_utils import extract_data
from grydgets.widgets.base import ContainerWidget, WidgetUpdaterThread, UpdaterWidget


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
    def __init__(
        self, size, color=(0, 0, 0), image_path=None, drop_shadow=False, **kwargs
    ):
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
            mask_surface = mask.to_surface(
                setcolor=(0, 0, 0, 255), unsetcolor=(0, 0, 0, 0)
            )
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
        image_path=None,
        drop_shadow=False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.rows = rows
        self.columns = columns
        self.padding = padding
        self.color = color
        self.widget_color = widget_color
        self.corner_radius = corner_radius
        self.widget_corner_radius = widget_corner_radius
        self.drop_shadow = drop_shadow
        if row_ratios is not None:
            self.row_ratios = row_ratios
        else:
            self.row_ratios = [1] * self.rows

        if column_ratios is not None:
            self.column_ratios = column_ratios
        else:
            self.column_ratios = [1] * self.columns

        self.image = None
        self.image_path = image_path

        self.surface = None
        self.widget_surface = None

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
            self.widget_surface = pygame.Surface(self.size, pygame.SRCALPHA, 32)
            if self.image is not None:
                self.image = load_and_scale_image(self.image_path, size)

        if not (self.is_dirty() or self.dirty):
            return self.surface

        if self.image is None and self.image_path is not None:
            self.image = load_and_scale_image(self.image_path, size)

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

                # final_widget_surface = (
                #     final_widget_surface.convert_alpha().premul_alpha()
                # )

            try:
                if self.logger.getEffectiveLevel() == logging.DEBUG:
                    start_time = time.time()
                    widget_surf = widget.render(size=widget_size)
                    end_time = time.time()
                    execution_time = end_time - start_time
                    widget.logger.debug(
                        f"Execution time of rendering myself: {execution_time:.5f} seconds"
                    )
                else:
                    widget_surf = widget.render(size=widget_size)
                final_widget_surface.blit(
                    widget_surf,
                    (0, 0),
                    # special_flags=pygame.BLEND_PREMULTIPLIED,
                )
                self.widget_surface.fill((0, 0, 0, 0), pygame.Rect(coords, widget_size))
                # self.surface = self.surface.premul_alpha()
                self.widget_surface.blit(
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

        if self.image is not None:
            self.surface.blit(self.image, (0, 0))
        else:
            self.surface.fill(self.color or (0, 0, 0, 0))

        if self.drop_shadow:
            mask = pygame.mask.from_surface(self.widget_surface, threshold=200)
            mask_surface = mask.to_surface(
                setcolor=(0, 0, 0, 255), unsetcolor=(0, 0, 0, 0)
            )
            white_mask_surface = mask.to_surface(
                setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0)
            )
            blurred_mask_surface = pygame.transform.gaussian_blur(
                mask_surface, radius=5
            )
            blurred_mask_surface.blit(
                white_mask_surface,
                (0, 0),
                special_flags=pygame.BLEND_RGBA_SUB,
            )

            self.surface.blit(blurred_mask_surface, (0, 0))
            self.surface.blit(blurred_mask_surface, (0, 0))
            self.surface.blit(blurred_mask_surface, (0, 0))

        self.surface.blit(self.widget_surface, (0, 0))

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


class ScheduleFlipWidget(FlipWidget):
    def __init__(self, schedule=None, **kwargs):
        super().__init__(**kwargs)
        self.current_widget = None
        self.schedule = schedule or {}
        self.destination_widget = None

    @lru_cache
    def get_current_widget(self, current_time):
        # Convert schedule to sorted list of (time, widget) tuples
        time_widgets = []
        for time_str, widget in self.schedule.items():
            hour, minute = map(int, time_str.split(":"))
            time_widgets.append((datetime_time(hour, minute), widget))

        # Sort by time
        time_widgets.sort(key=lambda x: x[0])

        # Find the active widget
        for i, (sched_time, widget) in enumerate(time_widgets):
            next_time = time_widgets[(i + 1) % len(time_widgets)][0]

            # Handle overnight periods (when next_time < sched_time)
            if next_time <= sched_time:
                # This period spans midnight
                if current_time >= sched_time or current_time < next_time:
                    return list(map(lambda x: x.name, self.widget_list)).index(widget)
            else:
                # Normal period within same day
                if sched_time <= current_time < next_time:
                    return list(map(lambda x: x.name, self.widget_list)).index(widget)

        return None

    def tick(self):
        if self.current_widget is None:
            self.current_widget = self.get_current_widget(datetime.now().time())
        current_widget = self.get_current_widget(datetime.now().time())
        if current_widget != self.current_widget:
            if not self.moving:  # This allows for the current animation to complete
                self.moving = True
                self.destination_widget = current_widget
                self.ticker = time.time()
                self.last_update = int(time.time())

        if self.moving:
            for widget in (
                self.widget_list[self.current_widget],
                self.widget_list[self.destination_widget],
            ):
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
            next_widget = self.widget_list[self.destination_widget]

            surface.blit(
                current_widget.render(size), (-(size[0] * transition_percentage), 0)
            )
            surface.blit(
                next_widget.render(size), (size[0] * (1 - transition_percentage), 0)
            )

            if time.time() - self.ticker >= self.transition:
                self.moving = False
                self.current_widget = self.destination_widget

            return surface
        else:
            return self.widget_list[self.current_widget].render(size)


class PillWidget(ContainerWidget):
    """A container widget that superimposes a second widget in a pill shape on top of the first.

    The first widget serves as the base/background, and the second widget is displayed
    in a pill-shaped overlay that can be positioned and sized as needed.
    """

    def __init__(
        self,
        circular_mask=False,
        widget_background_color=None,
        pill_background_color=None,
        pill_width_percent=0.8,
        pill_height_percent=0.2,
        pill_position_x=0.5,
        pill_position_y=0.8,
        pill_corner_radius=None,
        pill_size_relative_to_circle=False,
        **kwargs,
    ):
        """Initialize the Pill widget.

        Args:
            circular_mask: If True, apply circular masking to the first (base) widget
            pill_background_color: Background color of the pill (None = transparent)
            pill_width_percent: Width of pill as percentage of container (0.0-1.0)
            pill_height_percent: Height of pill as percentage of container (0.0-1.0)
            pill_position_x: X position of pill center as percentage (0.0-1.0)
            pill_position_y: Y position of pill center as percentage (0.0-1.0)
            pill_corner_radius: Corner radius for pill (None = fully rounded/semicircular ends)
            pill_size_relative_to_circle: If True, pill size is relative to circle diameter
            **kwargs: Additional widget parameters
        """
        super().__init__(**kwargs)
        self.circular_mask = circular_mask
        self.widget_background_color = widget_background_color
        self.pill_background_color = pill_background_color
        self.pill_width_percent = pill_width_percent
        self.pill_height_percent = pill_height_percent
        self.pill_position_x = pill_position_x
        self.pill_position_y = pill_position_y
        self.pill_corner_radius = pill_corner_radius
        self.pill_size_relative_to_circle = pill_size_relative_to_circle

    def add_widget(self, widget):
        """Add a child widget. Only accepts exactly 2 children."""
        if len(self.widget_list) >= 2:
            raise Exception("PillWidget can only have exactly two children")
        super().add_widget(widget)

    def is_dirty(self):
        """Check if widget needs re-rendering.

        Returns True if either child widget is dirty, since changes to either
        require re-rendering the entire composition.
        """
        if len(self.widget_list) < 2:
            return self.dirty
        return self.dirty or any(widget.is_dirty() for widget in self.widget_list)

    def tick(self):
        """Update both child widgets."""
        for widget in self.widget_list:
            widget.tick()

    @benchmark
    def render(self, size):
        """Render the widget with pill overlay."""
        if len(self.widget_list) != 2:
            # Not fully initialized yet
            surface = pygame.Surface(size, pygame.SRCALPHA, 32)
            surface.fill((0, 0, 0, 0))
            return surface

        self.size = size
        surface = pygame.Surface(size, pygame.SRCALPHA, 32)
        surface.fill((0, 0, 0, 0))

        # Render the base (first) widget
        base_widget = self.widget_list[0]
        base_surface = None

        # Apply circular mask to base widget if requested
        if self.circular_mask:
            # Create a circular mask
            mask_surface = pygame.Surface(size, pygame.SRCALPHA, 32)
            mask_surface.fill((0, 0, 0, 0))

            # Draw a circle in the center
            radius = min(size[0], size[1]) // 2
            center = (size[0] // 2, size[1] // 2)
            pygame.draw.circle(mask_surface, (255, 255, 255, 255), center, radius)

            base_surface = base_widget.render([radius * 2, radius * 2])

            # Create a temporary surface for the masked base
            masked_base = pygame.Surface(size, pygame.SRCALPHA, 32)
            if self.widget_background_color is not None:
                masked_base.fill(self.widget_background_color)
            else:
                masked_base.fill((0, 0, 0, 0))
            masked_base.blit(base_surface, (center[0] - radius, 0))
            masked_base.blit(mask_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            base_surface = masked_base
        else:
            base_surface = base_widget.render(size)

        # Blit the base widget
        surface.blit(base_surface, (0, 0))

        # Calculate pill dimensions and position
        if self.pill_size_relative_to_circle:
            # Calculate relative to circle diameter (min dimension)
            circle_diameter = min(size[0], size[1])
            pill_width = int(circle_diameter * self.pill_width_percent)
            pill_height = int(circle_diameter * self.pill_height_percent)
        else:
            # Calculate relative to container size
            pill_width = int(size[0] * self.pill_width_percent)
            pill_height = int(size[1] * self.pill_height_percent)
        pill_size = (pill_width, pill_height)

        # Calculate pill position (centered at specified percentage)
        pill_x = int(size[0] * self.pill_position_x - pill_width / 2)
        pill_y = int(size[1] * self.pill_position_y - pill_height / 2)
        pill_position = (pill_x, pill_y)

        # Create the pill surface
        pill_surface = pygame.Surface(pill_size, pygame.SRCALPHA, 32)
        pill_surface.fill((0, 0, 0, 0))

        # Draw the pill background if specified
        if self.pill_background_color is not None:
            # Determine corner radius
            if self.pill_corner_radius is None:
                # Make it fully pill-shaped (semicircular ends)
                corner_radius = pill_height // 2
            else:
                corner_radius = self.pill_corner_radius

            pygame.draw.rect(
                pill_surface,
                self.pill_background_color,
                pygame.Rect((0, 0), pill_size),
                border_radius=corner_radius,
            )

        # Render the pill content (second widget)
        pill_widget = self.widget_list[1]
        pill_content = pill_widget.render(pill_size)
        pill_surface.blit(pill_content, (0, 0))

        # Blit the pill onto the main surface
        surface.blit(pill_surface, pill_position)

        self.dirty = False
        return surface


class HTTPFlipWidget(FlipWidget, UpdaterWidget):
    def __init__(
        self,
        url,
        mapping,
        default_widget,
        json_path=None,
        jq_expression=None,
        auth=None,
        method=None,
        payload=None,
        **kwargs,
    ):
        self.destination_widget = None
        self.mapping = mapping
        self.default_widget = 0
        self.default_widget_name = default_widget

        self.url = url
        self.json_path = json_path
        self.jq_expression = jq_expression
        self.update_frequency = 5
        self.value = ""
        self.method = method or "GET"
        self.payload = payload

        self.requests_kwargs = {"headers": {}}
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
                self.requests_kwargs["headers"][
                    "Authorization"
                ] = f"Basic {encoded_auth}"
        if self.method == "POST" and self.payload:
            self.requests_kwargs["json"] = self.payload
        # This needs to happen at the end because it actually starts the update thread
        super().__init__(**kwargs)
        self.current_widget = None

    def add_widget(self, widget):
        super().add_widget(widget)
        if widget.name == self.default_widget_name:
            self.default_widget = len(self.widget_list) - 1

    @lru_cache
    def get_current_widget(self, response_value):
        if response_value in self.mapping:
            self.logger.debug(
                f"Mapped {response_value} to {self.mapping[response_value]}, or {list(map(lambda x: x.name, self.widget_list)).index(self.mapping[response_value])}"
            )
            return list(map(lambda x: x.name, self.widget_list)).index(
                self.mapping[response_value]
            )
        else:
            self.logger.debug(f"No mapping for {response_value}")
            return self.default_widget

    def tick(self):
        if self.current_widget is None:
            self.current_widget = self.get_current_widget(self.value)
            if self.current_widget is None:
                self.current_widget = self.default_widget
        current_widget = self.get_current_widget(self.value)
        if current_widget is None:
            current_widget = self.current_widget

        if current_widget != self.current_widget:
            if not self.moving:  # This allows for the current animation to complete
                self.moving = True
                self.destination_widget = current_widget
                self.ticker = time.time()
                self.last_update = int(time.time())

        if self.moving:
            for widget in (
                self.widget_list[self.current_widget],
                self.widget_list[self.destination_widget],
            ):
                widget.tick()
        else:
            self.widget_list[self.current_widget].tick()

    def update(self):
        """Perform HTTP request and determine target widget"""
        try:
            response = requests.request(
                method=self.method, url=self.url, **self.requests_kwargs
            )

            if response.status_code != 200:
                self.logger.warning(f"HTTP error: {response.status_code}")
                return

            # Extract the value from response
            if self.json_path is not None or self.jq_expression is not None:
                try:
                    response_json = response.json()
                    self.value = str(
                        extract_data(
                            response_json,
                            json_path=self.json_path,
                            jq_expression=self.jq_expression,
                        )
                    )
                except Exception as e:
                    self.logger.error(f"JSON extraction error: {e}")
                    return
            else:
                self.value = response.text.strip()

            self.logger.debug(f"Response '{self.value}'")

        except requests.ConnectionError as e:
            self.logger.warning(f"Connection error: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")

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
            next_widget = self.widget_list[self.destination_widget]

            surface.blit(
                current_widget.render(size), (-(size[0] * transition_percentage), 0)
            )
            surface.blit(
                next_widget.render(size), (size[0] * (1 - transition_percentage), 0)
            )

            if time.time() - self.ticker >= self.transition:
                self.moving = False
                self.current_widget = self.destination_widget

            return surface
        else:
            return self.widget_list[self.current_widget].render(size)
