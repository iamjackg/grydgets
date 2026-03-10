from functools import lru_cache

import pygame


class FontCache:
    @lru_cache(maxsize=32)
    def get_font(self, name, size):
        return pygame.font.Font(name, size)
