import logging

from rich.console import Console
from rich.highlighter import ReprHighlighter
from rich.theme import Theme

soft_theme = Theme({
    "repr.number": "rgb(180,200,255)",
    "repr.bool_true": "rgb(140,230,140)",
    "repr.bool_false": "rgb(230,140,140)",
    "repr.none": "rgb(200,200,200) italic",
    "repr.path": "rgb(190,220,160)",
    "repr.filename": "rgb(160,210,190)",
    "repr.url": "rgb(130,180,255) underline",
    "repr.uuid": "rgb(200,180,220)",
    "repr.attrib_name": "rgb(220,200,130)",
    "repr.attrib_value": "rgb(170,190,220)",
    "repr.str": "rgb(140,180,140)",
    "repr.tag_name": "rgb(200,170,220)",
    "repr.tag_value": "rgb(170,200,220)",

    "repr.time": "rgb(160,190,220) italic",
})

rich_console = Console(
    theme=soft_theme,
    force_terminal=True,
    no_color=False,
    highlight=True,
    width=150,
)

level_colors = {
    logging.DEBUG: "steel_blue",
    logging.INFO: "light_sea_green",
    logging.WARNING: "orange3",
    logging.ERROR: "indian_red",
    logging.CRITICAL: "bold medium_violet_red",
}


class LevelColorFilter(logging.Filter):
    def filter(self, record):
        color = level_colors.get(record.levelno, "default")
        record.levelname_color_open_tag = f"[{color}]"
        record.levelname_color_close_tag = "[/]"
        return True


class ExtendedReprHighlighter(ReprHighlighter):
    highlights = ReprHighlighter.highlights + [
        r"(?P<time>\b([01]?[0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:[.,]\d{1,9})?\b)",
    ]
