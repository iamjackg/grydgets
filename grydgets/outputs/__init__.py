"""Output sinks for Grydgets.

Outputs receive rendered surfaces and present them via display, file, or network.
"""

import logging
from typing import Any

import pygame


class Output:
    """Base class for output sinks."""

    preferred_fps: int = 1
    needs_display: bool = False

    def __init__(self, **kwargs: Any) -> None:
        self.logger = logging.getLogger(type(self).__name__)
        self._pending_dirty = False

    def pre_init(self) -> None:
        """Set SDL environment variables. Called BEFORE pygame.init()."""

    def setup(self, screen_size: tuple[int, int]) -> pygame.Surface | None:
        """Called AFTER pygame.init(). Returns display surface if this output owns it."""
        return None

    def wants_update(self) -> bool:
        """Does this output want a frame right now?"""
        return False

    def on_frame(self, surface: pygame.Surface, freshly_rendered: bool) -> None:
        """Receive the rendered surface.

        Args:
            surface: The current frame.
            freshly_rendered: True if re-rendered this frame (False = identical to last).
        """

    def stop(self) -> None:
        """Clean shutdown."""


OUTPUT_TYPES: dict[str, type[Output]] = {}


def register_output(name: str):
    """Decorator to register an output type."""
    def decorator(cls):
        OUTPUT_TYPES[name] = cls
        return cls
    return decorator


def create_outputs(output_configs: list[dict], render_config: dict) -> list[Output]:
    """Create output instances from configuration.

    Args:
        output_configs: List of output config dicts, each with a 'type' key.
        render_config: Global render settings (resolution, fps-limit, etc.).

    Returns:
        List of Output instances.
    """
    # Import concrete types to trigger registration
    from grydgets.outputs import window  # noqa: F401
    from grydgets.outputs import framebuffer  # noqa: F401
    from grydgets.outputs import file  # noqa: F401
    from grydgets.outputs import post  # noqa: F401

    outputs = []
    display_count = 0

    for output_conf in output_configs:
        output_type = output_conf["type"]
        if output_type not in OUTPUT_TYPES:
            raise ValueError(
                f"Unknown output type '{output_type}'. "
                f"Available: {list(OUTPUT_TYPES.keys())}"
            )

        cls = OUTPUT_TYPES[output_type]
        if cls.needs_display:
            display_count += 1

        kwargs = {k: v for k, v in output_conf.items() if k != "type"}
        kwargs["render_config"] = render_config
        outputs.append(cls(**kwargs))

    if display_count > 1:
        raise ValueError(
            "At most one display output (window or framebuffer) is allowed."
        )

    if not outputs:
        raise ValueError("At least one output must be configured.")

    return outputs
