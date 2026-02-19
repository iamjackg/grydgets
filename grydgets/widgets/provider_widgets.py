"""Widgets that use data providers."""

import base64
import io
import logging
import threading
import time

import pygame
import requests

from grydgets.json_utils import extract_data
from grydgets.widgets.base import Widget, ContainerWidget
from grydgets.widgets.text import TextWidget
from grydgets.widgets.image import ImageWidget
from grydgets.widgets.containers import FlipWidget


class ProviderWidget(Widget):
    """Widget that displays data from a provider with format string.

    Similar to RESTWidget but reads from a provider instead of making HTTP calls.
    """

    def __init__(
        self,
        providers,
        data_path=None,
        jq_expression=None,
        format_string="{value}",
        fallback_text="--",
        show_errors=False,
        font_path=None,
        text_size=None,
        vertical_align="center",
        **kwargs,
    ):
        """Initialize the provider widget.

        Args:
            providers: Dict of provider_name -> DataProvider
            data_path: JSON path to extract from provider data
            jq_expression: jq expression to extract from provider data
            format_string: Format string for display (default: "{value}")
            fallback_text: Text to show on error or missing data (default: "--")
            show_errors: If True, show error messages instead of fallback (default: False)
            font_path: Font path for text rendering
            text_size: Text size
            vertical_align: Vertical alignment (top, center, bottom)
            **kwargs: Additional widget parameters
        """
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

        # Track when we last checked the provider
        self.last_seen_timestamp = 0

        # Text widget for rendering
        self.text_widget = TextWidget(
            font_path=font_path,
            color=(255, 255, 255),
            padding=6,
            text_size=text_size,
            align="center",
            vertical_align=vertical_align,
            **kwargs,
        )

    def is_dirty(self):
        """Check if widget needs re-rendering."""
        # Check if provider data has been updated
        if self.provider.get_timestamp() > self.last_seen_timestamp:
            return True
        return self.text_widget.is_dirty()

    def render(self, size):
        """Render the widget."""
        self.size = size

        # Update timestamp
        self.last_seen_timestamp = self.provider.get_timestamp()

        # Check for errors
        error = self.provider.get_error()
        if error:
            if self.show_errors:
                text = f"Error: {error}"
            else:
                text = self.fallback_text
        else:
            # Get data from provider
            data = self.provider.get_data()
            if data is None:
                text = self.fallback_text
            else:
                # Extract value from data path or jq expression
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
    """Widget that renders data using Home Assistant templates.

    Supports multiple providers with namespaced variables.
    """

    def __init__(
        self,
        providers,
        template,
        hass_url,
        hass_token,
        fallback_text="--",
        font_path=None,
        text_size=None,
        vertical_align="center",
        **kwargs,
    ):
        """Initialize the provider template widget.

        Args:
            providers: Dict of provider_name -> DataProvider
            template: Jinja2 template string
            hass_url: Home Assistant URL
            hass_token: Home Assistant authentication token
            fallback_text: Text to show on error (default: "--")
            font_path: Font path for text rendering
            text_size: Text size
            vertical_align: Vertical alignment
            **kwargs: Additional widget parameters
        """
        super().__init__(**kwargs)

        if not providers:
            raise ValueError("ProviderTemplateWidget requires at least one provider")

        self.providers = providers
        self.template = template
        self.hass_url = hass_url.rstrip("/")
        self.hass_token = hass_token
        self.fallback_text = fallback_text

        # Track when we last checked providers
        self.last_seen_timestamps = {name: 0 for name in providers.keys()}

        # Text widget for rendering
        self.text_widget = TextWidget(
            font_path=font_path,
            color=(255, 255, 255),
            padding=6,
            text_size=text_size,
            align="center",
            vertical_align=vertical_align,
            **kwargs,
        )

    def is_dirty(self):
        """Check if widget needs re-rendering."""
        # Check if any provider data has been updated
        for name, provider in self.providers.items():
            if provider.get_timestamp() > self.last_seen_timestamps[name]:
                return True
        return self.text_widget.is_dirty()

    def render(self, size):
        """Render the widget."""
        self.size = size

        # Update timestamps
        for name, provider in self.providers.items():
            self.last_seen_timestamps[name] = provider.get_timestamp()

        # Build template with provider data
        try:
            # Collect all provider data
            provider_data = {}
            for name, provider in self.providers.items():
                data = provider.get_data()
                if data is None:
                    # If any provider has no data, use fallback
                    text = self.fallback_text
                    self.text_widget.set_text(text)
                    return self.text_widget.render(size)
                provider_data[f"provider_{name}"] = data

            # Build template with set statements
            template_lines = []
            for var_name, data in provider_data.items():
                # Convert data to Jinja2 variable assignment
                # This is a simple approach - might need refinement for complex data
                template_lines.append(f"{{% set {var_name} = {data} %}}")

            template_lines.append(self.template)
            full_template = "\n".join(template_lines)

            # Call Home Assistant template API
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
    """Widget that conditionally displays children based on provider data.

    Similar to HTTPFlipWidget but reads from a provider instead of HTTP calls.
    """

    def __init__(
        self,
        providers,
        data_path=None,
        jq_expression=None,
        mapping=None,
        default_widget=None,
        **kwargs,
    ):
        """Initialize the provider flip widget.

        Args:
            providers: Dict of provider_name -> DataProvider
            data_path: JSON path to extract value from provider data
            jq_expression: jq expression to extract value from provider data
            mapping: Dict mapping values to widget names
            default_widget: Name of widget to show by default
            **kwargs: Additional widget parameters (transition, ease, etc.)
        """
        super().__init__(**kwargs)

        if not providers or len(providers) != 1:
            raise ValueError("ProviderFlipWidget requires exactly one provider")

        self.providers = providers
        self.provider = list(providers.values())[0]
        self.data_path = data_path
        self.jq_expression = jq_expression
        self.mapping = mapping
        self.default_widget = 0
        self.default_widget_name = default_widget

        # Track when we last checked the provider
        self.last_seen_timestamp = 0
        self.current_value = None

        # Will be set to None initially, then resolved in tick()
        self.current_widget = None
        self.destination_widget = None

    def add_widget(self, widget):
        """Add a child widget."""
        super().add_widget(widget)
        if widget.name == self.default_widget_name:
            self.default_widget = len(self.widget_list) - 1

    def get_current_widget(self, value):
        """Map a provider value to a widget index.

        Args:
            value: The value from the provider

        Returns:
            Widget index, or None if no mapping found
        """
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

    def tick(self):
        """Update widget state based on provider data."""
        # Initialize current widget on first tick
        if self.current_widget is None:
            self.current_widget = self.default_widget

        # Check if provider data has changed
        provider_timestamp = self.provider.get_timestamp()
        if provider_timestamp > self.last_seen_timestamp:
            self.last_seen_timestamp = provider_timestamp

            # Get data from provider
            data = self.provider.get_data()
            error = self.provider.get_error()

            if error or data is None:
                # On error, stay on current widget (don't switch)
                self.logger.debug(
                    f"Provider error or no data, staying on current widget"
                )
            else:
                # Extract value from data path or jq expression
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

                    # Check if value changed
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
                    # On extraction error, stay on current widget

        # Tick children
        if self.moving:
            for widget in (
                self.widget_list[self.current_widget],
                self.widget_list[self.destination_widget],
            ):
                widget.tick()
        else:
            self.widget_list[self.current_widget].tick()

    def render(self, size):
        """Render the widget."""
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


class ProviderImageWidget(Widget):
    """Widget that displays images from URLs in provider data.

    Similar to RESTImageWidget but reads URL from a provider.
    """

    def __init__(
        self,
        providers,
        data_path=None,
        jq_expression=None,
        fallback_image=None,
        auth=None,
        preserve_aspect_ratio=False,
        **kwargs,
    ):
        """Initialize the provider image widget.

        Args:
            providers: Dict of provider_name -> DataProvider
            data_path: JSON path to extract image URL from provider data
            jq_expression: jq expression to extract image URL from provider data
            fallback_image: Path to fallback image file
            auth: Authentication dict for image fetching (same format as REST)
            preserve_aspect_ratio: If True, maintain original image aspect ratio when scaling
            **kwargs: Additional widget parameters
        """
        super().__init__(**kwargs)

        if not providers or len(providers) != 1:
            raise ValueError("ProviderImageWidget requires exactly one provider")

        self.providers = providers
        self.provider = list(providers.values())[0]
        self.data_path = data_path
        self.jq_expression = jq_expression
        self.fallback_image = fallback_image

        # Track when we last checked the provider
        self.last_seen_timestamp = 0
        self.current_image_url = None

        # Image widget for rendering
        self.image_widget = ImageWidget(
            preserve_aspect_ratio=preserve_aspect_ratio, **kwargs
        )

        # Load fallback image if provided
        if fallback_image:
            try:
                with open(fallback_image, "rb") as f:
                    self.image_widget.set_image(f.read())
            except Exception as e:
                self.logger.warning(f"Failed to load fallback image: {e}")

        # Build request kwargs for image fetching
        self.requests_kwargs = {"headers": {}}
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

    def is_dirty(self):
        """Check if widget needs re-rendering."""
        # Check if provider data has been updated
        if self.provider.get_timestamp() > self.last_seen_timestamp:
            return True
        return self.image_widget.is_dirty()

    def render(self, size):
        """Render the widget."""
        self.size = size

        # Check if provider data has changed
        provider_timestamp = self.provider.get_timestamp()
        if provider_timestamp > self.last_seen_timestamp:
            self.last_seen_timestamp = provider_timestamp

            # Get data from provider
            data = self.provider.get_data()
            error = self.provider.get_error()

            if not error and data is not None:
                # Extract image URL from data path or jq expression
                try:
                    if self.data_path or self.jq_expression:
                        image_url = extract_data(
                            data,
                            json_path=self.data_path,
                            jq_expression=self.jq_expression,
                        )
                    else:
                        image_url = data

                    # Only fetch if URL changed
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

    def _fetch_image(self, url):
        """Fetch image from URL or load from local file.

        Args:
            url: Image URL (http://, https://, or file://)
        """
        try:
            # Handle file:// URLs for local images
            if url.startswith("file://"):
                file_path = url[7:]  # Remove 'file://' prefix
                self.logger.debug(f"Loading image from local file: {file_path}")

                with open(file_path, "rb") as f:
                    image_data = f.read()

                # Clear old image data before setting new one
                self.image_widget.image_data = None
                self.image_widget.old_surface = None

                self.image_widget.set_image(image_data)
                self.logger.debug(f"Loaded image from {file_path}")
            else:
                # Handle HTTP/HTTPS URLs
                response = requests.get(url, **self.requests_kwargs, timeout=5)
                if response.status_code == 200:
                    # Clear old image data before setting new one
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
