from __future__ import annotations

import logging
import random
import threading
import time
from typing import Any


class Widget(object):
    def __init__(self, size: tuple[int, int] | None = None, name: str | None = None, **kwargs: Any) -> None:
        self.size: tuple[int, int] = size if size is not None else (0, 0)
        self.dirty = True
        self.logger = logging.getLogger(
            kwargs.get("unique_name") or name or type(self).__name__
        )
        self.unique_name = kwargs.get("unique_name") or name or type(self).__name__
        self.name = name or type(self).__name__

    def is_dirty(self) -> bool:
        return self.dirty

    def tick(self) -> None:
        pass

    def render(self, size: tuple[int, int]) -> Any:
        if self.size != size:
            self.size = size
            self.dirty = True


class ContainerWidget(Widget):
    def __init__(self, size: tuple[int, int] | None = None, **kwargs: Any) -> None:
        super().__init__(size=size, **kwargs)
        self.widget_list: list[Widget] = list()

    def is_dirty(self) -> bool:
        return self.dirty or any([widget.is_dirty() for widget in self.widget_list])

    def add_widget(self, widget: Widget) -> None:
        self.widget_list.append(widget)

    def tick(self) -> None:
        for widget in self.widget_list:
            widget.tick()


class UpdaterWidget(Widget):
    def __init__(self, update_frequency: int = 30, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.update_frequency = kwargs.get("update_frequency", update_frequency)
        self.update_thread = WidgetUpdaterThread(self, self.update_frequency, **kwargs)

        self.update()
        self.update_thread.start()

    def stop(self) -> None:
        self.update_thread.stop()
        self.logger.debug("waiting for thread to terminate")
        self.update_thread.join()
        self.logger.debug("thread joined")

    def update(self) -> None:
        pass


class WidgetUpdaterThread(threading.Thread):
    def __init__(self, widget: "UpdaterWidget", frequency: int, **kwargs: Any) -> None:
        super(WidgetUpdaterThread, self).__init__()
        self._stop_event = threading.Event()
        self.widget = widget
        self.frequency = frequency
        self.last_update = int(time.time())
        self.logger = logging.getLogger(
            (kwargs.get("unique_name") or type(self).__name__) + "WidgetUpdaterThread"
        )

        self.logger.debug("Initialized")

    def stop(self) -> None:
        self.logger.debug("Received stop event")
        self._stop_event.set()

    def run(self) -> None:
        try:
            while not self._stop_event.is_set():
                now = int(time.time())
                if now - self.last_update >= self.frequency:
                    jitter = random.randint(0, min(self.frequency // 2, 15))
                    self.last_update = now
                    if self._stop_event.wait(timeout=jitter):
                        break
                    self.logger.debug("Updating")
                    self.widget.update()
                self._stop_event.wait(1)
        except Exception as e:
            self.logger.warning(str(e))
