"""Data providers for Grydgets.

Providers fetch data in the background and make it available to widgets.
This allows multiple widgets to share the same data source without
redundant API calls.
"""

from grydgets.providers.base import DataProvider
from grydgets.providers.rest import RestDataProvider
from grydgets.providers.manager import ProviderManager

__all__ = ['DataProvider', 'RestDataProvider', 'ProviderManager']
