"""Base classes for data providers."""

import logging
import random
import threading
import time


class DataProvider:
    """Fetches data on a background thread so multiple widgets can share one
    instance instead of each polling the API themselves."""

    def __init__(self, update_interval=60, jitter=0, **kwargs):
        self.update_interval = update_interval
        # Randomizes fetch timing so providers on the same interval don't all hit the API at once.
        self.jitter = jitter
        self.name = kwargs.get('name', type(self).__name__)

        self.lock = threading.Lock()
        self.data = None
        self.last_update_time = 0
        self.error_state = None

        self._stop_event = threading.Event()
        self._thread = None

        self.logger = logging.getLogger(f"{type(self).__name__}({self.name})")

    def start(self):
        if self._thread is not None:
            self.logger.warning("Provider already started")
            return

        self.logger.info("Starting provider")
        self._thread = threading.Thread(target=self._fetch_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.logger.info("Stopping provider")
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def get_data(self):
        with self.lock:
            return self.data

    def get_timestamp(self):
        with self.lock:
            return self.last_update_time

    def get_error(self):
        with self.lock:
            return self.error_state

    def _fetch_loop(self):
        self._perform_fetch()

        while not self._stop_event.is_set():
            sleep_time = self.update_interval
            if self.jitter > 0:
                sleep_time += random.uniform(0, self.jitter)

            if self._stop_event.wait(timeout=sleep_time):
                break

            self._perform_fetch()

    def _perform_fetch(self):
        try:
            self.logger.debug("Fetching data")
            new_data = self._fetch_data()

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
        raise NotImplementedError("Subclasses must implement _fetch_data()")
