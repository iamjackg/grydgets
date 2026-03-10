"""Widgets that use data providers."""
from __future__ import annotations

import base64
import io
import logging
import threading
import time
from typing import Any

import pygame
import requests

from grydgets.json_utils import extract_data
from grydgets.providers.base import DataProvider
from grydgets.widgets.base import Widget, ContainerWidget
from grydgets.widgets.text import TextWidget
from grydgets.widgets.image import ImageWidget
from grydgets.widgets.containers import FlipWidget


class ProviderWidget(Widget):
    """Widget that displays data from a provider with format string."""

    def __init__(
        self,
        providers: dict[str, DataProvider],
        data_path: str | None = None,
        jq_expression: str | None = None,
        format_string: str = "{value}",
        fallback_text: str = "--",
        show_errors: bool = False,
        font_path: str | None = None,
        text_size: int | None = None,
        vertical_align: str = "center",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)

        if not providers or len(providers) != 1:
            raise ValueError("ProviderWidget requires exactly one provider")

        self.providers = providers
        self.provider = list(providers.values())[0]
        self.data_path = data_path
        self.jq_expression = jq_expression
        self.format_string = format_string
        self.fallback_text = fallback_text
        self.show_errors = show_errors

        self.last_seen_timestamp = 0

        self.text_widget = TextWidget(
            font_path=font_path,
            color=(255, 255, 255),
            padding=6,
            text_size=text_size,
            align="center",
            vertical_align=vertical_align,
            **kwargs,
        )

    def is_dirty(self) -> bool:
        if self.provider.get_timestamp() > self.last_seen_timestamp:
            return True
        return self.text_widget.is_dirty()

    def render(self, size: tuple[int, int]) -> pygame.Surface:
        self.size = size

        self.last_seen_timestamp = self.provider.get_timestamp()

        error = self.provider.get_error()
        if error:
            if self.show_errors:
                text = f"Error: {error}"
            else:
                text = self.fallback_text
        else:
            data = self.provider.get_data()
            if data is None:
                text = self.fallback_text
            else:
                try:
                    if self.data_path or self.jq_expression:
                        value = extract_data(
                            data,
                            json_path=self.data_path,
                            jq_expression=self.jq_expression,
                        )
                    else:
                        value = data
                    text = self.format_string.format(value=value)
                except (
                    KeyError,
                    IndexError,
                    ValueError,
                    TypeError,
                    StopIteration,
                ) as e:
                    self.logger.debug(f"Failed to extract data: {e}")
                    text = self.fallback_text

        self.text_widget.set_text(text)
        return self.text_widget.render(size)


class ProviderTemplateWidget(Widget):
    """Widget that renders data using Home Assistant templates."""

    def __init__(
        self,
        providers: dict[str, DataProvider],
        template: str,
        hass_url: str,
        hass_token: str,
        fallback_text: str = "--",
        font_path: str | None = None,
        text_size: int | None = None,
        vertical_align: str = "center",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)

        if not providers:
            raise ValueError("ProviderTemplateWidget requires at least one provider")

        self.providers = providers
        self.template = template
        self.hass_url = hass_url.rstrip("/")
        self.hass_token = hass_token
        self.fallback_text = fallback_text

        self.last_seen_timestamps = {name: 0 for name in providers.keys()}

        self.text_widget = TextWidget(
            font_path=font_path,
            color=(255, 255, 255),
            padding=6,
            text_size=text_size,
            align="center",
            vertical_align=vertical_align,
            **kwargs,
        )

    def is_dirty(self) -> bool:
        for name, provider in self.providers.items():
            if provider.get_timestamp() > self.last_seen_timestamps[name]:
                return True
        return self.text_widget.is_dirty()

    def render(self, size: tuple[int, int]) -> pygame.Surface:
        self.size = size

        for name, provider in self.providers.items():
            self.last_seen_timestamps[name] = provider.get_timestamp()

        try:
            provider_data = {}
            for name, provider in self.providers.items():
                data = provider.get_data()
                if data is None:
                    text = self.fallback_text
                    self.text_widget.set_text(text)
                    return self.text_widget.render(size)
                provider_data[f"provider_{name}"] = data

            template_lines = []
            for var_name, data in provider_data.items():
                template_lines.append(f"{{% set {var_name} = {data} %}}")

            template_lines.append(self.template)
            full_template = "\n".join(template_lines)

            response = requests.post(
                f"{self.hass_url}/api/template",
                headers={
                    "Authorization": f"Bearer {self.hass_token}",
                    "Content-Type": "application/json",
                },
                json={"template": full_template},
                timeout=5,
            )

            if response.status_code != 200:
                self.logger.error(f"Home Assistant API error: {response.status_code}")
                text = self.fallback_text
            else:
                text = response.text.strip()

        except Exception as e:
            self.logger.error(f"Template rendering failed: {e}")
            text = self.fallback_text

        self.text_widget.set_text(text)
        return self.text_widget.render(size)


class ProviderFlipWidget(FlipWidget):
    """Widget that conditionally displays children based on provider data."""

    def __init__(
        self,
        providers: dict[str, DataProvider],
        data_path: str | None = None,
        jq_expression: str | None = None,
        mapping: dict[str, str] | None = None,
        default_widget: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)

        if not providers or len(providers) != 1:
            raise ValueError("ProviderFlipWidget requires exactly one provider")

        self.providers = providers
        self.provider = list(providers.values())[0]
        self.data_path = data_path
        self.jq_expression = jq_expression
        self.mapping: dict[str, str] = mapping or {}
        self.default_widget = 0
        self.default_widget_name = default_widget

        self.last_seen_timestamp = 0
        self.current_value: str | None = None

        self.current_widget = None
        self.destination_widget: int | None = None

    def add_widget(self, widget: Widget) -> None:
        super().add_widget(widget)
        if widget.name == self.default_widget_name:
            self.default_widget = len(self.widget_list) - 1

    def get_current_widget(self, value: str) -> int | None:
        if value in self.mapping:
            widget_name = self.mapping[value]
            try:
                return list(map(lambda x: x.name, self.widget_list)).index(widget_name)
            except ValueError:
                self.logger.error(f"Widget '{widget_name}' not found in children")
                return None
        else:
            self.logger.debug(f"No mapping for value '{value}'")
            return self.default_widget

    def tick(self) -> None:
        if self.current_widget is None:
            self.current_widget = self.default_widget

        provider_timestamp = self.provider.get_timestamp()
        if provider_timestamp > self.last_seen_timestamp:
            self.last_seen_timestamp = provider_timestamp

            data = self.provider.get_data()
            error = self.provider.get_error()

            if error or data is None:
                self.logger.debug(
                    f"Provider error or no data, staying on current widget"
                )
            else:
                try:
                    if self.data_path or self.jq_expression:
                        value = str(
                            extract_data(
                                data,
                                json_path=self.data_path,
                                jq_expression=self.jq_expression,
                            )
                        )
                    else:
                        value = str(data)

                    if value != self.current_value:
                        self.current_value = value
                        target_widget = self.get_current_widget(value)

                        if (
                            target_widget is not None
                            and target_widget != self.current_widget
                        ):
                            if not self.moving:
                                self.moving = True
                                self.destination_widget = target_widget
                                self.ticker = time.time()
                                self.last_update = int(time.time())
                                self.logger.debug(
                                    f"Value changed to '{value}', switching to widget {target_widget}"
                                )

                except (
                    KeyError,
                    IndexError,
                    ValueError,
                    TypeError,
                    StopIteration,
                ) as e:
                    self.logger.debug(f"Failed to extract data: {e}")

        if self.moving:
            assert self.current_widget is not None
            assert self.destination_widget is not None
            for widget in (
                self.widget_list[self.current_widget],
                self.widget_list[self.destination_widget],
            ):
                widget.tick()
        else:
            assert self.current_widget is not None
            self.widget_list[self.current_widget].tick()

    def render(self, size: tuple[int, int]) -> pygame.Surface:
        if self.moving:
            assert self.current_widget is not None
            assert self.destination_widget is not None
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
            assert self.current_widget is not None
            return self.widget_list[self.current_widget].render(size)


class ProviderImageWidget(Widget):
    """Widget that displays images from URLs in provider data."""

    def __init__(
        self,
        providers: dict[str, DataProvider],
        data_path: str | None = None,
        jq_expression: str | None = None,
        fallback_image: str | None = None,
        auth: dict[str, Any] | None = None,
        preserve_aspect_ratio: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)

        if not providers or len(providers) != 1:
            raise ValueError("ProviderImageWidget requires exactly one provider")

        self.providers = providers
        self.provider = list(providers.values())[0]
        self.data_path = data_path
        self.jq_expression = jq_expression
        self.fallback_image = fallback_image

        self.last_seen_timestamp = 0
        self.current_image_url: str | None = None

        self.image_widget = ImageWidget(
            preserve_aspect_ratio=preserve_aspect_ratio, **kwargs
        )

        if fallback_image:
            try:
                with open(fallback_image, "rb") as f:
                    self.image_widget.set_image(f.read())
            except Exception as e:
                self.logger.warning(f"Failed to load fallback image: {e}")

        self.requests_kwargs: dict[str, Any] = {"headers": {}}
        if auth is not None:
            if "bearer" in auth:
                self.requests_kwargs["headers"][
                    "Authorization"
                ] = f"Bearer {auth['bearer']}"
            elif "basic" in auth:
                username = auth["basic"].get("username", "")
                password = auth["basic"].get("password", "")
                auth_string = f"{username}:{password}"
                encoded_auth = base64.b64encode(auth_string.encode()).decode()
                self.requests_kwargs["headers"][
                    "Authorization"
                ] = f"Basic {encoded_auth}"

    def is_dirty(self) -> bool:
        if self.provider.get_timestamp() > self.last_seen_timestamp:
            return True
        return self.image_widget.is_dirty()

    def render(self, size: tuple[int, int]) -> pygame.Surface:
        self.size = size

        provider_timestamp = self.provider.get_timestamp()
        if provider_timestamp > self.last_seen_timestamp:
            self.last_seen_timestamp = provider_timestamp

            data = self.provider.get_data()
            error = self.provider.get_error()

            if not error and data is not None:
                try:
                    if self.data_path or self.jq_expression:
                        image_url = extract_data(
                            data,
                            json_path=self.data_path,
                            jq_expression=self.jq_expression,
                        )
                    else:
                        image_url = data

                    if image_url != self.current_image_url:
                        self.current_image_url = image_url
                        self._fetch_image(image_url)

                except (
                    KeyError,
                    IndexError,
                    ValueError,
                    TypeError,
                    StopIteration,
                ) as e:
                    self.logger.error(f"Failed to extract image URL: {e}")

        return self.image_widget.render(size)

    def _fetch_image(self, url: str) -> None:
        try:
            if url.startswith("file://"):
                file_path = url[7:]
                self.logger.debug(f"Loading image from local file: {file_path}")

                with open(file_path, "rb") as f:
                    image_data = f.read()

                self.image_widget.image_data = None
                self.image_widget.old_surface = None

                self.image_widget.set_image(image_data)
                self.logger.debug(f"Loaded image from {file_path}")
            else:
                response = requests.get(url, **self.requests_kwargs, timeout=5)
                if response.status_code == 200:
                    self.image_widget.image_data = None
                    self.image_widget.old_surface = None

                    self.image_widget.set_image(response.content)
                    self.logger.debug(f"Fetched image from {url}")
                else:
                    self.logger.warning(
                        f"Failed to fetch image: HTTP {response.status_code}"
                    )
        except FileNotFoundError:
            self.logger.warning(f"File not found: {url}")
        except Exception as e:
            self.logger.warning(f"Failed to fetch image: {e}")
