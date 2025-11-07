import base64
import io
import logging
import threading

import pygame
import requests

from grydgets.json_utils import extract_data
from grydgets.widgets.base import Widget, UpdaterWidget


class ImageWidget(Widget):
    def __init__(self, image_data=None, preserve_aspect_ratio=False, **kwargs):
        super().__init__(**kwargs)
        self.image_update_lock = threading.Lock()
        self.image_data = image_data
        self.preserve_aspect_ratio = preserve_aspect_ratio
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

            if self.preserve_aspect_ratio:
                # Calculate scaling ratios for both dimensions
                width_ratio = self.size[0] / original_size[0]
                height_ratio = self.size[1] / original_size[1]

                # Use the smaller ratio to ensure image fits within container
                scale_ratio = min(width_ratio, height_ratio)

                # Scale both dimensions using the same ratio
                final_size = (
                    int(original_size[0] * scale_ratio),
                    int(original_size[1] * scale_ratio)
                )
            else:
                # Original behavior: fit image to container
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
    def __init__(self, url, json_path=None, jq_expression=None, auth=None, preserve_aspect_ratio=False, **kwargs):
        self.url = url
        self.json_path = json_path
        self.jq_expression = jq_expression
        self.update_frequency = 30
        self.image_widget = ImageWidget(preserve_aspect_ratio=preserve_aspect_ratio)

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
                self.requests_kwargs["headers"]["Authorization"] = f"Basic {encoded_auth}"
        # This needs to happen at the end because it actually starts the update thread
        super().__init__(**kwargs)

    def is_dirty(self):
        return self.image_widget.is_dirty()

    def update(self):
        try:
            # Check if main URL is a file:// URL
            if self.url.startswith("file://"):
                file_path = self.url[7:]  # Remove 'file://' prefix
                self.logger.debug(f"Loading image from local file: {file_path}")

                with open(file_path, "rb") as f:
                    image_data = f.read()

                self.logger.debug("Updated from local file")
            else:
                # Handle HTTP/HTTPS URLs
                response = requests.get(self.url, **self.requests_kwargs)
                if self.json_path is not None or self.jq_expression is not None:
                    response_json = response.json()
                    image_url = extract_data(
                        response_json,
                        json_path=self.json_path,
                        jq_expression=self.jq_expression
                    )

                    # Check if extracted URL is a file:// URL
                    if image_url.startswith("file://"):
                        file_path = image_url[7:]  # Remove 'file://' prefix
                        self.logger.debug(f"Loading image from local file: {file_path}")

                        with open(file_path, "rb") as f:
                            image_data = f.read()
                    else:
                        image_response = requests.get(image_url)
                        image_data = image_response.content
                else:
                    image_data = response.content

                self.logger.debug("Updated")

            # Clear old image data before setting new one
            self.image_widget.image_data = None
            self.image_widget.old_surface = None

            self.image_widget.set_image(image_data)
        except FileNotFoundError as e:
            self.logger.warning("File not found: {}".format(e))
        except Exception as e:
            self.logger.warning("Could not update: {}".format(e))

    def render(self, size):
        # self.image_widget.set_image(self.image_data)

        return self.image_widget.render(size)
