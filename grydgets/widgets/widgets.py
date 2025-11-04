import inspect
import itertools
import logging
import pprint
import sys

from grydgets.widgets.base import Widget, ContainerWidget, UpdaterWidget
import grydgets.widgets.image
import grydgets.widgets.text
import grydgets.widgets.containers
import grydgets.widgets.notifiable
import grydgets.widgets.provider_widgets
from grydgets.widgets.containers import HTTPFlipWidget


class WidgetManager:
    def __init__(self, provider_manager=None):
        self._name_to_widget_map = {}
        self.name_to_instance = {}
        self.provider_manager = provider_manager
        self.map_all_the_widgets_in_here()

    def window(self, seq, n=2):
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

    def map_all_the_widgets_in_here(self):
        all_widget_members = []
        for module in ["containers", "image", "notifiable", "text", "provider_widgets"]:
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
                    self._name_to_widget_map[class_name] = obj

    def create_widget_tree(self, widget_dictionary, path=None, counter=None):
        if path is None:
            path = []
        if counter is None:
            counter = {}

        widget_type_name = widget_dictionary["widget"]
        widget_name = widget_dictionary.get("name") or widget_type_name
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

        # Resolve providers if specified
        if "providers" in widget_parameters and self.provider_manager:
            provider_list = widget_parameters["providers"]
            if not isinstance(provider_list, list):
                provider_list = [provider_list]

            # Validate and resolve providers
            self.provider_manager.validate_providers(provider_list)
            provider_dict = {
                name: self.provider_manager.get_provider(name)
                for name in provider_list
            }
            widget_parameters["providers"] = provider_dict

        widget = self._name_to_widget_map[widget_type_name](**widget_parameters)
        if hasattr(widget, "notify"):
            if callable(widget.notify):
                if widget_name not in self.name_to_instance:
                    self.name_to_instance[widget_name] = widget
                else:
                    logging.warning(
                        f"Warning: Duplicate widget name '{widget_name}'. "
                        "Not adding to list of notifiable widgets."
                    )
            else:
                logging.warning(
                    f"Warning: 'notify' attribute of widget '{widget_name}' "
                    f"is not callable. Skipping."
                )

        if "children" in widget_dictionary:
            child_counter = {}  # Reset counter for children
            for child in widget_dictionary["children"]:
                widget.add_widget(
                    self.create_widget_tree(
                        child,
                        path + [f"{widget_name}{counter[widget_name]}"],
                        child_counter,
                    )
                )

        return widget

    def recursively_stop_widgets(self, main_widget):
        if isinstance(main_widget, ContainerWidget):
            for widget in main_widget.widget_list:
                logging.debug(f"Going deeper in {main_widget}")
                self.stop_all_widgets(widget)
        if isinstance(main_widget, UpdaterWidget):
            logging.debug(f"Stopping UpdaterWidget {main_widget}")
            main_widget.stop()

        del main_widget

    def stop_all_widgets(self, main_widget):
        self.recursively_stop_widgets(main_widget)
        self.name_to_instance = {}
