import queue
import time

from grydgets.widgets.base import ContainerWidget
from grydgets.widgets.text import TextWidget


class NotifiableTextWidget(ContainerWidget):
    def __init__(
        self, font_path=None, text_size=None, padding=0, color=(255, 255, 255), **kwargs
    ):
        super().__init__(**kwargs)
        self.showing_text = False
        self.last_update = None
        self.rendering_start = None
        self.newly_created_text = False
        self.notification_queue = queue.Queue()
        self.notification_duration = 5

        self.text_widget = TextWidget(
            font_path=font_path,
            text_size=text_size,
            text="",
            color=color,
            align="center",
            vertical_align="center",
            padding=padding,
            **kwargs
        )

    def add_widget(self, widget):
        if self.widget_list:
            raise Exception("NotifiableTextWidget can only have one child")
        else:
            self.logger.debug("Adding widget")
            super().add_widget(widget)

    def notify(self, data):
        self.logger.debug("Received notification")
        self.notification_queue.put(data)

    def is_dirty(self):
        if self.showing_text:
            return self.dirty
        else:
            return self.widget_list[0].is_dirty()

    def tick(self):
        if (
            self.showing_text
            and self.rendering_start is not None
            and time.time() - self.rendering_start >= self.notification_duration
        ):
            self.showing_text = False
            self.rendering_start = None
            self.dirty = True
        else:
            self.widget_list[0].tick()

        if not self.showing_text:
            try:
                data = self.notification_queue.get(block=False)
                self.logger.debug("Processing notification queue")
            except queue.Empty:
                pass
            else:
                if "text" in data:
                    self.last_update = int(time.time())
                    self.showing_text = True
                    self.text_widget.set_text(data["text"])
                    if "color" in data:
                        self.text_widget.set_color(data["color"])
                    self.notification_duration = data.get("duration", 5)
                    self.dirty = True

    def render(self, size):
        if self.showing_text:
            if self.rendering_start is None:
                self.rendering_start = time.time()
            return self.text_widget.render(size)
        else:
            return self.widget_list[0].render(size)
