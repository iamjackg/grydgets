import logging
import threading
import time


class Widget(object):
    def __init__(self, size=None):
        self.size = size
        self.dirty = True

    def is_dirty(self):
        return self.dirty

    def tick(self):
        pass

    def render(self, size):
        if self.size != size:
            self.size = size
            self.dirty = True


class ContainerWidget(Widget):
    def __init__(self, size=None):
        super().__init__(size)
        self.widget_list = list()

    def is_dirty(self):
        return self.dirty or any([widget.is_dirty() for widget in self.widget_list])

    def add_widget(self, widget):
        self.widget_list.append(widget)

    def tick(self):
        for widget in self.widget_list:
            widget.tick()


class UpdaterWidget(Widget):
    def __init__(self):
        super().__init__()
        self.update_frequency = 30
        self.update_thread = WidgetUpdaterThread(self, self.update_frequency)

        self.update()
        self.update_thread.start()

    def stop(self):
        self.update_thread.stop()
        logging.debug('{} waiting for thread to terminate'.format(self))
        self.update_thread.join()
        logging.debug('{} joined'.format(self))

    def update(self):
        pass


class WidgetUpdaterThread(threading.Thread):
    def __init__(self, widget, frequency):
        super(WidgetUpdaterThread, self).__init__()
        self._stop_event = threading.Event()
        self.widget = widget
        self.frequency = frequency
        self.last_update = int(time.time())

        logging.debug('Initialized {}'.format(self))

    def stop(self):
        self._stop_event.set()

    def run(self):
        try:
            while not self._stop_event.is_set():
                now = int(time.time())
                if now - self.last_update >= self.frequency:
                    logging.debug('Updating {}'.format(self.widget))
                    self.widget.update()
                    self.last_update = now
                time.sleep(0.1)
        except Exception as e:
            logging.warning(str(e))