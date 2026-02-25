import logging


class ColoredFormatter(logging.Formatter):

    COLOR_CODES = {
        'DEBUG': '\033[38;5;67m',  # steel_blue
        'INFO': '\033[38;5;79m',  # light_sea_green
        'WARNING': '\033[38;5;172m',  # orange
        'ERROR': '\033[38;5;131m',  # indian_red
        'CRITICAL': '\033[38;5;162m',  # medium_violet_red
        'RESET': '\033[0m',
    }

    def format(self, record):
        levelname = record.levelname
        if levelname in self.COLOR_CODES:
            record.levelname = f"{self.COLOR_CODES[levelname]}{levelname}{self.COLOR_CODES['RESET']}"
        return super().format(record)
