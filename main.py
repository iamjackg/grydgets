import os
import signal
import pygame
from pygame.transform import rotate
import logging
import time
import threading
from flask import Flask, request, jsonify

from grydgets import config
from grydgets.widgets.containers import ScreenWidget
from grydgets.widgets.widgets import WidgetManager
from grydgets.providers import ProviderManager

logging.basicConfig(
    format="[%(asctime)s] %(levelname)s:%(name)s:%(message)s", level=logging.DEBUG
)


def load_widget_tree():
    return config.load_yaml("widgets.yaml")


widget_tree = load_widget_tree()
conf = config.load_config("conf.yaml")

# Check for headless mode before setting display environment variables
headless_mode = conf.get("headless", {}).get("enabled", False)

if headless_mode:
    os.environ["SDL_VIDEODRIVER"] = "dummy"
elif "fb-device" in conf["graphics"]:
    os.environ["SDL_FBDEV"] = conf["graphics"]["fb-device"]

if not headless_mode and "x-display" in conf["graphics"]:
    os.environ["DISPLAY"] = conf["graphics"]["x-display"]

fps_limit = conf["graphics"]["fps-limit"]

pygame_flags = 0
pygame_flags |= pygame.DOUBLEBUF

if conf["graphics"]["fullscreen"]:
    pygame_flags |= pygame.FULLSCREEN
    pygame_flags |= pygame.HWSURFACE

logging.getLogger().setLevel(logging.getLevelName(conf["logging"]["level"].upper()))

stop_everything = threading.Event()
reload_lock = threading.Lock()

pygame.init()
pygame.mixer.quit()

if not headless_mode:
    pygame.mouse.set_visible(0)

screen_size = tuple(conf["graphics"]["resolution"])

if headless_mode:
    # In headless mode, create a dummy surface instead of a display
    screen = None
else:
    screen = pygame.display.set_mode(screen_size, pygame_flags)
    pygame.display.set_caption("Grydgets dashboard", "Grydgets")

# Initialize and start providers
provider_manager = ProviderManager('providers.yaml')
provider_manager.start_all()

widget_manager = WidgetManager(provider_manager)

screen_widget = ScreenWidget(
    screen_size,
    image_path=widget_tree.get("background_image", None),
    color=widget_tree.get("background_color", (0, 0, 0)),
    drop_shadow=widget_tree.get("drop_shadow", False),
)

screen_widget.add_widget(widget_manager.create_widget_tree(widget_tree["widgets"][0]))

# Headless mode helper functions
def setup_headless_output_directory(output_path):
    """Create headless output directory if it doesn't exist."""
    os.makedirs(output_path, exist_ok=True)
    logging.info(f"Headless output directory: {output_path}")


def get_headless_filename(pattern, image_format, sequence):
    """Generate filename from pattern with timestamp and sequence."""
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = pattern.format(timestamp=timestamp, sequence=sequence)
    return f"{filename}.{image_format}"


def cleanup_old_images(output_path, keep_images, image_format):
    """Remove old images if keep_images limit is set."""
    if keep_images == 0:
        return
    image_files = sorted(
        [f for f in os.listdir(output_path) if f.endswith(f".{image_format}") and not f.startswith("latest.")],
        key=lambda x: os.path.getmtime(os.path.join(output_path, x))
    )
    while len(image_files) > keep_images:
        oldest = image_files.pop(0)
        os.remove(os.path.join(output_path, oldest))
        logging.debug(f"Removed old image: {oldest}")


def update_latest_symlink(filepath, output_path, image_format):
    """Update 'latest.{format}' symlink to point to newest image."""
    symlink_path = os.path.join(output_path, f"latest.{image_format}")
    try:
        if os.path.islink(symlink_path) or os.path.exists(symlink_path):
            os.remove(symlink_path)
        os.symlink(os.path.basename(filepath), symlink_path)
        logging.debug(f"Updated latest symlink: {symlink_path}")
    except Exception as e:
        logging.warning(f"Failed to update symlink: {e}")


def save_headless_image(surface, conf, sequence):
    """Save rendered surface to file in headless mode."""
    headless_conf = conf["headless"]
    output_path = headless_conf["output_path"]
    image_format = headless_conf["image_format"]
    pattern = headless_conf.get("filename_pattern", "grydgets_{timestamp}")

    filename = get_headless_filename(pattern, image_format, sequence)
    filepath = os.path.join(output_path, filename)

    try:
        # JPEG needs alpha channel stripped
        if image_format in ["jpg", "jpeg"]:
            temp_surface = pygame.Surface(surface.get_size())
            temp_surface.blit(surface, (0, 0))
            pygame.image.save(temp_surface, filepath)
        else:
            pygame.image.save(surface, filepath)

        logging.info(f"Saved headless render: {filename}")

        # Update latest symlink if enabled
        if headless_conf.get("create_latest_symlink", True):
            update_latest_symlink(filepath, output_path, image_format)

        # Cleanup old images
        keep_images = headless_conf.get("keep_images", 100)
        if keep_images > 0:
            cleanup_old_images(output_path, keep_images, image_format)

    except Exception as e:
        logging.error(f"Failed to save headless image: {e}")


# Flask app for notifications
app = Flask(__name__)


@app.route("/notify", methods=["POST"])
def widget():
    payload = request.get_json()
    requested_widget = payload["widget"]
    if requested_widget not in widget_manager.name_to_instance:
        return jsonify({"success": False, "error": "Widget not found"}), 400

    widget_manager.name_to_instance[requested_widget].notify(payload)
    return jsonify({"success": True})


def run_server():
    app.run(host="0.0.0.0", port=conf["server"]["port"])


server_thread = threading.Thread(target=run_server)
server_thread.daemon = True
server_thread.start()

# Initialize headless variables
if headless_mode:
    setup_headless_output_directory(conf["headless"]["output_path"])
    # Set to 0 to trigger immediate render on first loop iteration
    last_headless_save = 0
    headless_image_sequence = 0


def reload_configuration(signum, frame):
    global screen_widget, widget_tree, provider_manager, widget_manager, last_headless_save, headless_image_sequence
    logging.info("Reloading configuration...")
    with reload_lock:
        try:
            new_conf = config.load_config("conf.yaml")
            new_headless_mode = new_conf.get("headless", {}).get("enabled", False)

            # Check if headless mode toggle changed
            if new_headless_mode != headless_mode:
                logging.warning("Headless mode toggle changed. This requires a restart. Ignoring configuration reload.")
                return

            # If headless output_path changed, create new directory and reset sequence
            if headless_mode:
                old_output_path = conf["headless"]["output_path"]
                new_output_path = new_conf["headless"]["output_path"]
                if old_output_path != new_output_path:
                    setup_headless_output_directory(new_output_path)
                    headless_image_sequence = 0

            new_widget_tree = load_widget_tree()
            logging.info("Stopping all widgets...")
            widget_manager.stop_all_widgets(screen_widget)

            # Stop old providers
            logging.info("Stopping all providers...")
            provider_manager.stop_all()

            # Create and start new providers
            logging.info("Starting new providers...")
            provider_manager = ProviderManager('providers.yaml')
            provider_manager.start_all()

            # Create new widget manager with new providers
            widget_manager = WidgetManager(provider_manager)

            screen_widget = ScreenWidget(
                screen_size,
                image_path=new_widget_tree.get("background_image", None),
                color=new_widget_tree.get("background_color", (0, 0, 0)),
                drop_shadow=new_widget_tree.get("drop_shadow", False),
            )
            screen_widget.add_widget(widget_manager.create_widget_tree(new_widget_tree["widgets"][0]))
            widget_tree = new_widget_tree
            logging.info("Configuration reloaded successfully.")
        except Exception as e:
            logging.error(f"Failed to reload configuration: {e}")


signal.signal(signal.SIGUSR1, reload_configuration)

fps_time = time.time()
frame_data = list()
last_screen_surface = None
while not stop_everything.is_set():
    frame_start = time.time()
    try:
        # Skip event handling in headless mode
        if not headless_mode:
            for event in pygame.event.get():
                if event.type in [pygame.QUIT, pygame.MOUSEBUTTONDOWN]:
                    stop_everything.set()

        with reload_lock:
            # Always tick widgets for updates (clocks, animations)
            screen_widget.tick()

            if headless_mode:
                # Only render when it's time to save an image
                current_time = time.time()
                render_interval = conf["headless"]["render_interval"]

                if current_time - last_headless_save >= render_interval:
                    # Render and save
                    if conf["graphics"].get("flip", False):
                        surface = rotate(screen_widget.render(screen_size), 180)
                    else:
                        surface = screen_widget.render(screen_size)

                    save_headless_image(surface, conf, headless_image_sequence)
                    last_headless_save = current_time
                    headless_image_sequence += 1
            else:
                # Normal mode: render when dirty and update display
                if not last_screen_surface or screen_widget.is_dirty():
                    if conf["graphics"].get("flip", False):
                        last_screen_surface = rotate(screen_widget.render(screen_size), 180)
                    else:
                        last_screen_surface = screen_widget.render(screen_size)

                    screen.blit(last_screen_surface, (0, 0))
                    pygame.display.flip()

        sleep_time = max((1 / fps_limit) - (time.time() - frame_start), 0)
        # if sleep_time == 0:
        #     logging.debug('Losing frames {}'.format(sleep_time))
        time.sleep(sleep_time)
    except KeyboardInterrupt:
        stop_everything.set()

    frame_end = time.time()
    frame_data.append(frame_end - frame_start)
    if time.time() - fps_time > 0.5:
        logging.debug("FPS: {}".format(1 / (sum(frame_data) / len(frame_data))))
        fps_time = time.time()
        frame_data = list()

widget_manager.stop_all_widgets(screen_widget)
provider_manager.stop_all()
pygame.quit()
