"""HTTP POST output — push rendered frames to an endpoint."""

import io
import threading
import time
from typing import Any

import pygame
import requests

from grydgets.outputs import Output, register_output


@register_output("post")
class PostOutput(Output):
    needs_display = False
    preferred_fps = 1

    def __init__(
        self,
        url: str,
        image_format: str = "png",
        trigger: str = "on_dirty",
        min_interval: int = 60,
        auth: dict | None = None,
        multipart: dict | None = None,
        after_post: dict | None = None,
        render_config: dict | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.url = url
        self.image_format = image_format
        self.trigger = trigger
        self.min_interval = min_interval
        self.auth = auth
        self.multipart = multipart
        self.after_post = after_post
        self._last_post_time = 0
        self._worker_thread: threading.Thread | None = None

    def wants_update(self) -> bool:
        if self._worker_thread and self._worker_thread.is_alive():
            return False
        return (time.time() - self._last_post_time) >= self.min_interval

    def on_frame(self, surface: pygame.Surface, freshly_rendered: bool) -> None:
        if self.trigger == "on_dirty" and not freshly_rendered:
            return

        # Encode in main thread (pygame surface access is not thread-safe)
        image_bytes = self._encode_surface(surface)

        self._last_post_time = time.time()
        self._worker_thread = threading.Thread(
            target=self._do_post, args=(image_bytes,), daemon=True
        )
        self._worker_thread.start()

    def _encode_surface(self, surface: pygame.Surface) -> bytes:
        buf = io.BytesIO()
        if self.image_format in ("jpg", "jpeg"):
            temp = pygame.Surface(surface.get_size())
            temp.blit(surface, (0, 0))
            pygame.image.save(temp, buf, f"image.{self.image_format}")
        else:
            pygame.image.save(surface, buf, f"image.{self.image_format}")
        return buf.getvalue()

    def _do_post(self, image_bytes: bytes) -> None:
        try:
            headers: dict[str, str] = {}
            kwargs: dict[str, Any] = {}

            if self.auth:
                if "bearer" in self.auth:
                    headers["Authorization"] = f"Bearer {self.auth['bearer']}"
                elif "basic" in self.auth:
                    kwargs["auth"] = (
                        self.auth["basic"].get("username", ""),
                        self.auth["basic"].get("password", ""),
                    )

            if self.multipart:
                field_name = self.multipart.get("field_name", "file")
                filename = self.multipart.get("filename")
                if not filename or filename == "image":
                    filename = f"image.{self.image_format}"
                content_type = "image/jpeg" if self.image_format in ("jpg", "jpeg") else f"image/{self.image_format}"
                kwargs["files"] = {field_name: (filename, image_bytes, content_type)}
            else:
                content_type = "image/jpeg" if self.image_format in ("jpg", "jpeg") else f"image/{self.image_format}"
                headers["Content-Type"] = content_type
                kwargs["data"] = image_bytes

            response = requests.post(
                self.url, headers=headers, timeout=30, **kwargs
            )
            self.logger.debug(f"POST {self.url} -> {response.status_code}")

            if response.ok and self.after_post:
                self._do_after_post()
        except Exception as e:
            self.logger.warning(f"POST {self.url} failed: {e}")

    def _do_after_post(self) -> None:
        try:
            method = self.after_post.get("method", "GET")
            url = self.after_post["url"]
            response = requests.request(method, url, timeout=30)
            self.logger.debug(f"after_post {method} {url} -> {response.status_code}")
        except Exception as e:
            self.logger.warning(f"after_post failed: {e}")

    def stop(self) -> None:
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5)
