"""Manager for data providers."""

import logging
import os

from grydgets.config import load_providers_config
from grydgets.providers.rest import RestDataProvider


class ProviderManager:
    """Loads providers.yaml, creates provider instances, and manages their
    lifecycle and lookup by name."""

    PROVIDER_TYPES = {
        'rest': RestDataProvider,
    }

    def __init__(self, config_path='providers.yaml'):
        self.config_path = config_path
        self.providers = {}
        self.logger = logging.getLogger('ProviderManager')

        if os.path.exists(config_path):
            self._load_providers()
        else:
            self.logger.info(f"No providers config found at {config_path}")

    def _load_providers(self):
        try:
            config = load_providers_config(self.config_path)
        except Exception as e:
            self.logger.error(f"Failed to load providers config: {e}")
            raise

        if not config or 'providers' not in config:
            self.logger.warning("No providers defined in config")
            return

        providers_config = config['providers']

        for name, provider_config in providers_config.items():
            try:
                self._create_provider(name, provider_config)
            except Exception as e:
                self.logger.error(f"Failed to create provider '{name}': {e}")
                raise

    def _create_provider(self, name, config):
        if not isinstance(config, dict):
            raise ValueError(f"Provider '{name}' config must be a dictionary")

        provider_type = config.get('type')
        if not provider_type:
            raise ValueError(f"Provider '{name}' missing 'type' field")

        provider_class = self.PROVIDER_TYPES.get(provider_type)
        if not provider_class:
            raise ValueError(
                f"Unknown provider type '{provider_type}' for provider '{name}'. "
                f"Available types: {list(self.PROVIDER_TYPES.keys())}"
            )

        provider_kwargs = dict(config)
        del provider_kwargs['type']
        provider_kwargs['name'] = name

        provider = provider_class(**provider_kwargs)
        self.providers[name] = provider

        self.logger.info(f"Created provider '{name}' of type '{provider_type}'")

    def start_all(self):
        self.logger.info(f"Starting {len(self.providers)} providers")
        for name, provider in self.providers.items():
            try:
                provider.start()
            except Exception as e:
                self.logger.error(f"Failed to start provider '{name}': {e}")
                raise

    def stop_all(self):
        self.logger.info(f"Stopping {len(self.providers)} providers")
        for name, provider in self.providers.items():
            try:
                provider.stop()
            except Exception as e:
                self.logger.warning(f"Error stopping provider '{name}': {e}")

    def get_provider(self, name):
        if name not in self.providers:
            raise KeyError(
                f"Provider '{name}' not found. "
                f"Available providers: {list(self.providers.keys())}"
            )
        return self.providers[name]

    def has_provider(self, name):
        return name in self.providers

    def validate_providers(self, required_providers):
        missing = [name for name in required_providers if name not in self.providers]
        if missing:
            raise ValueError(
                f"Missing required providers: {missing}. "
                f"Available providers: {list(self.providers.keys())}"
            )
