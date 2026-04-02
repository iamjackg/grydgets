"""Direct framebuffer output."""

import os
from typing import Any

import pygame

from grydgets.outputs import Output, register_output


@register_output("framebuffer")
class FramebufferOutput(Output):
    needs_display = True

    def __init__(self, device: str = "/dev/fb1", render_config: dict | None = None,
                 **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.device = device
        self.preferred_fps = (render_config or {}).get("fps-limit", 10)
        self._display_surface: pygame.Surface | None = None

    def pre_init(self) -> None:
        os.environ["SDL_FBDEV"] = self.device

    def setup(self, screen_size: tuple[int, int]) -> pygame.Surface:
        flags = pygame.DOUBLEBUF | pygame.FULLSCREEN | pygame.HWSURFACE
        pygame.mouse.set_visible(0)
        self._display_surface = pygame.display.set_mode(screen_size, flags)
        return self._display_surface

    def wants_update(self) -> bool:
        return True

    def on_frame(self, surface: pygame.Surface, freshly_rendered: bool) -> None:
        if freshly_rendered and self._display_surface is not None:
            self._display_surface.blit(surface, (0, 0))
            pygame.display.flip()
