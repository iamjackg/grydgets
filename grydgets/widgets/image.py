import io
import logging
import threading

import pygame
import requests

from grydgets.json_utils import extract_json_path
from grydgets.widgets.base import Widget, UpdaterWidget


class ImageWidget(Widget):
    def __init__(self, image_data=None, **kwargs):
        super().__init__(**kwargs)
        self.image_update_lock = threading.Lock()
        self.image_data = image_data
        self.old_surface = None
        self.dirty = True

    def set_image(self, image_data):
        if image_data != self.image_data:
            with self.image_update_lock:
                self.image_data = image_data
            self.dirty = True

    def render(self, size):
        super().render(size)

        if self.image_data is None:
            self.old_surface = pygame.Surface(self.size, pygame.SRCALPHA, 32)
        elif self.dirty:
            try:
                with self.image_update_lock:
                    loaded_image_surface = pygame.image.load(
                        io.BytesIO(self.image_data)
                    )
            except pygame.error:
                with self.image_update_lock:
                    self.image_data = None
                return self.old_surface

            original_size = loaded_image_surface.get_size()
            adjusted_sizes = list()

            for picture_axis, container_axis in zip(original_size, self.size):
                if picture_axis != container_axis:
                    ratio = picture_axis / container_axis
                    adjusted_sizes.append(
                        tuple(
                            int(original_axis / ratio)
                            for original_axis in original_size
                        )
                    )

            final_size = self.size
            for adjusted_size in adjusted_sizes:
                if (
                    adjusted_size[0] <= self.size[0]
                    and adjusted_size[1] <= self.size[1]
                ):
                    final_size = adjusted_size
                    break

            resized_picture = pygame.transform.smoothscale(
                loaded_image_surface, final_size
            )
            picture_position = (
                (self.size[0] - final_size[0]) / 2,
                (self.size[1] - final_size[1]) / 2,
            )

            final_surface = pygame.Surface(self.size, pygame.SRCALPHA, 32)
            final_surface.blit(resized_picture, picture_position)
            self.old_surface = final_surface

        self.dirty = False
        return self.old_surface


class RESTImageWidget(UpdaterWidget):
    def __init__(self, url, json_path=None, auth=None, **kwargs):
        self.url = url
        self.json_path = json_path
        self.update_frequency = 30
        self.image_widget = ImageWidget()

        self.requests_kwargs = {"headers": {}}
        if auth is not None:
            if "bearer" in auth:
                self.requests_kwargs["headers"]["Authorization"] = "Bearer {}".format(
                    auth["bearer"]
                )
        # This needs to happen at the end because it actually starts the update thread
        super().__init__(**kwargs)

    def is_dirty(self):
        return self.image_widget.is_dirty()

    def update(self):
        try:
            response = requests.get(self.url, **self.requests_kwargs)
            if self.json_path is not None:
                response_json = response.json()
                image_url = extract_json_path(response_json, self.json_path)

                image_response = requests.get(image_url)
                image_data = image_response.content
            else:
                image_data = response.content
        except Exception as e:
            self.logger.warning("Could not update: {}".format(e))
            return

        self.logger.debug("Updated")

        self.image_widget.set_image(image_data)

    def render(self, size):
        # self.image_widget.set_image(self.image_data)

        return self.image_widget.render(size)
