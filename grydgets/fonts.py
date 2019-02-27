import pygame


class FontCache(object):
    def __init__(self):
        self.font_cache = dict()

    def get_font(self, name, size):
        try:
            return self.font_cache[(name, size)]
        except KeyError:
            self.font_cache[(name, size)] = pygame.font.Font(name, size)
            return self.font_cache[(name, size)]
