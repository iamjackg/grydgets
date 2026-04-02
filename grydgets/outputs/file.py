"""File output — save rendered frames to disk."""

import os
import time
from typing import Any

import pygame

from grydgets.outputs import Output, register_output


@register_output("file")
class FileOutput(Output):
    needs_display = False
    preferred_fps = 1

    def __init__(
        self,
        output_path: str = "./headless_output",
        render_interval: int = 60,
        image_format: str = "png",
        filename_pattern: str = "grydgets_{timestamp}",
        keep_images: int = 100,
        create_latest_symlink: bool = True,
        render_config: dict | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.output_path = output_path
        self.render_interval = render_interval
        self.image_format = image_format
        self.filename_pattern = filename_pattern
        self.keep_images = keep_images
        self.create_latest_symlink = create_latest_symlink
        self._last_save_time = 0  # triggers immediate first save
        self._sequence = 0

    def setup(self, screen_size: tuple[int, int]) -> None:
        os.makedirs(self.output_path, exist_ok=True)
        self.logger.info(f"File output directory: {self.output_path}")

    def wants_update(self) -> bool:
        return (time.time() - self._last_save_time) >= self.render_interval

    def on_frame(self, surface: pygame.Surface, freshly_rendered: bool) -> None:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = self.filename_pattern.format(
            timestamp=timestamp, sequence=self._sequence
        )
        filename = f"{filename}.{self.image_format}"
        filepath = os.path.join(self.output_path, filename)

        try:
            if self.image_format in ("jpg", "jpeg"):
                temp = pygame.Surface(surface.get_size())
                temp.blit(surface, (0, 0))
                pygame.image.save(temp, filepath)
            else:
                pygame.image.save(surface, filepath)

            self.logger.info(f"Saved: {filename}")
            self._last_save_time = time.time()
            self._sequence += 1

            if self.create_latest_symlink:
                self._update_symlink(filepath)

            if self.keep_images > 0:
                self._cleanup_old_images()

        except Exception as e:
            self.logger.error(f"Failed to save image: {e}")

    def _update_symlink(self, filepath: str) -> None:
        symlink_path = os.path.join(self.output_path, f"latest.{self.image_format}")
        try:
            if os.path.islink(symlink_path) or os.path.exists(symlink_path):
                os.remove(symlink_path)
            os.symlink(os.path.basename(filepath), symlink_path)
        except Exception as e:
            self.logger.warning(f"Failed to update symlink: {e}")

    def _cleanup_old_images(self) -> None:
        fmt = self.image_format
        image_files = sorted(
            [
                f
                for f in os.listdir(self.output_path)
                if f.endswith(f".{fmt}") and not f.startswith("latest.")
            ],
            key=lambda x: os.path.getmtime(os.path.join(self.output_path, x)),
        )
        while len(image_files) > self.keep_images:
            oldest = image_files.pop(0)
            os.remove(os.path.join(self.output_path, oldest))
            self.logger.debug(f"Removed old image: {oldest}")
