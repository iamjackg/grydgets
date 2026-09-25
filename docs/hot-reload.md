# Hot reload

You can reload the configuration without restarting Grydgets by sending a `SIGUSR1` signal to the running process:

```bash
kill -SIGUSR1 <process_id>
```

Grydgets reads `conf.yaml`, `providers.yaml`, `widgets.yaml` and any theme files again, stops all the widgets and
providers, and starts them back up from the new configuration.

If you're using [day and night themes](configuration/conf-yaml.md#appearance-day-and-night-themes), whichever theme was showing stays up after the reload.

A few changes can't be applied this way, and Grydgets will log a warning and ask for a restart:

*   Adding or removing the `window` output. In this case the whole
    reload is skipped.
*   Starting or stopping the [HTTP server](configuration/conf-yaml.md#server), or changing its `host` or `port`. The
    rest of the reload still goes through.
