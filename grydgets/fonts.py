from collections import Counter

import pygame


class FontCache(object):
    def __init__(self):
        self.font_cache = dict()
        self.font_cache_usage = Counter()

    def get_font(self, name, size):
        if len(self.font_cache) > 5 and len(self.font_cache_usage) > 5:
            keys_to_delete = []
            for key, usage_count in self.font_cache_usage.items():
                if usage_count < 2:
                    keys_to_delete.append(key)

            for key in keys_to_delete:
                del self.font_cache_usage[key]
                del self.font_cache[key]

        self.font_cache_usage.update([(name, size)])
        try:
            return self.font_cache[(name, size)]
        except KeyError:
            self.font_cache[(name, size)] = pygame.font.Font(name, size)
            return self.font_cache[(name, size)]
