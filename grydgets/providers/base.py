"""Base classes for data providers."""

import logging
import random
import threading
import time


class DataProvider:
    """Base class for data providers that fetch data in background threads.

    Providers continuously fetch data and make it available to widgets.
    Multiple widgets can share the same provider to avoid redundant API calls.
    """

    def __init__(self, update_interval=60, jitter=0, **kwargs):
        """Initialize the data provider.

        Args:
            update_interval: Seconds between data fetches (default: 60)
            jitter: Random seconds to add to update interval (default: 0)
            **kwargs: Additional provider-specific configuration
        """
        self.update_interval = update_interval
        self.jitter = jitter
        self.name = kwargs.get('name', type(self).__name__)

        # Thread-safe data storage
        self.lock = threading.Lock()
        self.data = None
        self.last_update_time = 0
        self.error_state = None

        # Thread management
        self._stop_event = threading.Event()
        self._thread = None

        # Logging
        self.logger = logging.getLogger(f"{type(self).__name__}({self.name})")

    def start(self):
        """Start the background fetch thread."""
        if self._thread is not None:
            self.logger.warning("Provider already started")
            return

        self.logger.info("Starting provider")
        self._thread = threading.Thread(target=self._fetch_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the background fetch thread."""
        self.logger.info("Stopping provider")
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def get_data(self):
        """Get the current data (thread-safe).

        Returns:
            The current data, or None if not yet fetched or error occurred.
        """
        with self.lock:
            return self.data

    def get_timestamp(self):
        """Get the timestamp of the last successful update (thread-safe).

        Returns:
            Unix timestamp of last update, or 0 if never updated.
        """
        with self.lock:
            return self.last_update_time

    def get_error(self):
        """Get the current error state (thread-safe).

        Returns:
            Error message string, or None if no error.
        """
        with self.lock:
            return self.error_state

    def _fetch_loop(self):
        """Main fetch loop that runs in the background thread."""
        # Perform initial fetch immediately
        self._perform_fetch()

        while not self._stop_event.is_set():
            # Calculate next update time with jitter
            sleep_time = self.update_interval
            if self.jitter > 0:
                sleep_time += random.uniform(0, self.jitter)

            # Sleep with periodic checks for stop event
            if self._stop_event.wait(timeout=sleep_time):
                break

            self._perform_fetch()

    def _perform_fetch(self):
        """Perform a single fetch operation."""
        try:
            self.logger.debug("Fetching data")
            new_data = self._fetch_data()

            # Update with lock
            with self.lock:
                self.data = new_data
                self.last_update_time = time.time()
                self.error_state = None

            self.logger.debug("Fetch successful")

        except Exception as e:
            self.logger.error(f"Fetch failed: {e}")
            with self.lock:
                self.data = None
                self.error_state = str(e)

    def _fetch_data(self):
        """Fetch data from the source.

        This method must be implemented by subclasses.

        Returns:
            The fetched data.

        Raises:
            Exception: If fetch fails.
        """
        raise NotImplementedError("Subclasses must implement _fetch_data()")
