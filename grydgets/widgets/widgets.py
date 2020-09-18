import inspect
import itertools
import logging
import pprint
import sys

from grydgets.widgets.base import Widget, ContainerWidget, UpdaterWidget
import grydgets.widgets.image
import grydgets.widgets.text

_name_to_widget_map = {}


def window(seq, n=2):
    "Returns a sliding window (of width n) over data from the iterable"
    "   s -> (s0,s1,...s[n-1]), (s1,s2,...,sn), ...                   "
    it = iter(seq)
    result = tuple(itertools.islice(it, n))
    if len(result) == n:
        yield result
    for elem in it:
        result = result[1:] + (elem,)
        yield result


def map_all_the_widgets_in_here():
    all_widget_members = []
    for module in ["containers", "image", "text"]:
        all_widget_members += inspect.getmembers(
            sys.modules["grydgets.widgets." + module]
        )
    for name, obj in all_widget_members:
        if inspect.isclass(obj) and issubclass(obj, Widget):
            if "Widget" in obj.__name__:
                class_name = obj.__name__.split("Widget")[0].lower()
                if not class_name:
                    continue
                _name_to_widget_map[class_name] = obj


def create_widget_tree(widget_dictionary):
    widget_name = widget_dictionary["widget"]
    widget_parameters = {
        key: value
        for key, value in widget_dictionary.items()
        if key not in ["widget", "children"]
    }
    widget = _name_to_widget_map[widget_name](**widget_parameters)

    if "children" in widget_dictionary:
        for child in widget_dictionary["children"]:
            widget.add_widget(create_widget_tree(child))

    return widget


def stop_all_widgets(main_widget):
    if isinstance(main_widget, ContainerWidget):
        for widget in main_widget.widget_list:
            logging.debug("Going deeper in {}".format(main_widget))
            stop_all_widgets(widget)
    elif isinstance(main_widget, UpdaterWidget):
        logging.debug("Stopping UpdaterWidget {}".format(main_widget))
        main_widget.stop()


map_all_the_widgets_in_here()
