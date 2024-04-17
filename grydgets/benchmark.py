import logging
import time


def benchmark(func):
    def wrapper(self, *args, **kwargs):
        if self.logger.getEffectiveLevel() == logging.DEBUG:
            start_time = time.time()
            result = func(self, *args, **kwargs)
            end_time = time.time()
            execution_time = end_time - start_time
            self.logger.debug(
                f"Execution time of {func.__name__}: {execution_time:.5f} seconds"
            )
        else:
            result = func(self, *args, **kwargs)
        return result

    return wrapper
