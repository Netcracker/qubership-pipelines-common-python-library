import re
import click
import logging
import sys, os
from qubership_pipelines_common_library.v1.execution.exec_logger import ExecutionLogger

DEFAULT_CONTEXT_FILE_PATH = 'context.yaml'


def utils_cli(func):
    """Decorator to add CLI options for logging level, context path and custom input params."""
    @click.option('--log-level', default='INFO', show_default=True,
                  type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], case_sensitive=False),
                  help="Set the logging level")
    @click.option('--context_path', required=True, default=DEFAULT_CONTEXT_FILE_PATH, type=str, help="Path to context")
    @click.option("--input_params", "-p", multiple=True, callback=_input_params_to_dict,
                  help="Params to use instead of context as key-values. Nested keys are supported with double-underscores or dots as separators, e.g. -p params__group__key=value")
    @click.pass_context
    def wrapper(ctx, *args, log_level, **kwargs):
        ExecutionLogger.EXECUTION_LOG_LEVEL = getattr(logging, log_level.upper(), logging.INFO)
        _configure_global_logger(logging.getLogger(), log_level, ExecutionLogger.DEFAULT_FORMAT)
        _transform_kwargs(kwargs)
        return ctx.invoke(func, *args, **kwargs)
    return wrapper


def _configure_global_logger(global_logger: logging.Logger, log_level: str, formatter_str: str):
    """Configure the global logger with a specific log level and formatter."""
    log_level_value = getattr(logging, log_level.upper(), logging.INFO)
    global_logger.setLevel(logging.DEBUG)
    if global_logger.hasHandlers():
        global_logger.handlers.clear()
    global_logger.propagate = True
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(log_level_value)
    stdout_handler.setFormatter(logging.Formatter(formatter_str))
    global_logger.addHandler(stdout_handler)


def _transform_kwargs(kwargs):
    if kwargs.get("input_params"):
        kwargs.pop("context_path")


def _input_params_to_dict(ctx, param, values: tuple[str, ...]):
    result = {}
    for kvp in values:
        key, value = [item.strip() for item in kvp.split("=", 1)]
        if _validate_key(key):
            _set_item_by_path(result, key, _transform_value(value))
    return result if result else None


def _validate_key(key):
    return True


def _transform_value(value):
    return value


_KEY_PARTS_DELIMITER_PATTERN = re.compile(r'\.|__')
def _set_item_by_path(target_dict: dict, path, value):
    current_dict = target_dict
    key_parts = _KEY_PARTS_DELIMITER_PATTERN.split(path)
    for i, key in enumerate(key_parts):
        if i == len(key_parts) - 1:
            current_dict[key] = value
            break
        if not isinstance(current_dict.get(key), dict):
            current_dict[key] = {}
        current_dict = current_dict[key]
    return target_dict
