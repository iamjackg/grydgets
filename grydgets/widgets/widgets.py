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
    """Returns a sliding window (of width n) over data from the iterable
    s -> (s0,s1,...s[n-1]), (s1,s2,...,sn), ...
    """
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
        module_name = f"grydgets.widgets.{module}"
        all_widget_members.extend(inspect.getmembers(sys.modules[module_name]))
    for name, obj in all_widget_members:
        if (
            inspect.isclass(obj)
            and issubclass(obj, Widget)
            and "Widget" in obj.__name__
        ):
            class_name = obj.__name__.split("Widget")[0].lower()
            if class_name:
                _name_to_widget_map[class_name] = obj


def create_widget_tree(widget_dictionary, path=None, counter=None):
    if path is None:
        path = []
    if counter is None:
        counter = {}

    widget_name = widget_dictionary["widget"]
    # Increment or initialize the widget counter
    counter[widget_name] = counter.get(widget_name, 0) + 1

    # Generate a unique name based on the path and counter
    unique_name = "_".join(path + [f"{widget_name}{counter[widget_name]}"])
    widget_parameters = {
        key: value
        for key, value in widget_dictionary.items()
        if key not in ["widget", "children"]
    }
    logging.debug(f"Adding to widget tree: {unique_name}")
    # Pass the unique name as an extra parameter
    widget_parameters["unique_name"] = unique_name
    widget = _name_to_widget_map[widget_name](**widget_parameters)

    if "children" in widget_dictionary:
        child_counter = {}  # Reset counter for children
        for child in widget_dictionary["children"]:
            widget.add_widget(
                create_widget_tree(
                    child,
                    path + [f"{widget_name}{counter[widget_name]}"],
                    child_counter,
                )
            )

    return widget


def stop_all_widgets(main_widget):
    if isinstance(main_widget, ContainerWidget):
        for widget in main_widget.widget_list:
            logging.debug(f"Going deeper in {main_widget}")
            stop_all_widgets(widget)
    elif isinstance(main_widget, UpdaterWidget):
        logging.debug(f"Stopping UpdaterWidget {main_widget}")
        main_widget.stop()


map_all_the_widgets_in_here()
