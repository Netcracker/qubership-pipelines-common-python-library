import logging
import sys
import time
from functools import wraps
from typing import Callable


class RetryDecorator:

    def __init__(self, condition_func, retry_timeout_seconds: int = 180, retry_wait_seconds: int = 1):
        self.condition_func = condition_func
        self.retry_timeout_seconds = retry_timeout_seconds
        self.retry_wait_seconds = retry_wait_seconds
        self.logger = logging.getLogger()

    def __call__(self, func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            self._update_retry_timeout_seconds_from_kwargs(kwargs, func)
            self._update_retry_wait_seconds_from_kwargs(kwargs, func)

            count_seconds = 0
            retries = 0
            last_log_time = time.perf_counter()
            last_result = None
            estimated_max_attempts = self.retry_timeout_seconds // self.retry_wait_seconds


            while count_seconds < self.retry_timeout_seconds and not self.condition_func(last_result):
                try:
                    last_result = func(*args, **kwargs)
                    if self.condition_func(last_result):
                        self.logger.debug(f"Function {func.__name__} successfully executed after {retries} attempts in {count_seconds}s")
                        return last_result
                    retries += 1

                    now = time.perf_counter()
                    if now - last_log_time >= 10:
                        self._sleep_with_warning_log(
                            f"Made [{retries} of {estimated_max_attempts}] retries with {self.retry_wait_seconds} seconds between attempts. Trying to execute func: {self.condition_func.__name__}. {count_seconds} of {self.retry_timeout_seconds} seconds left")
                        last_log_time = now
                    else:
                        time.sleep(self.retry_wait_seconds)

                except Exception as e:
                    retries += 1
                    now = time.perf_counter()
                    if now - last_log_time >= 10:
                        self._process_exception_during_func_execution(e, count_seconds, func.__name__, retries, estimated_max_attempts)
                        last_log_time = now
                    else:
                        time.sleep(self.retry_wait_seconds)

                finally:
                    count_seconds += self.retry_wait_seconds

            if self.condition_func(last_result):
                self.logger.debug(f"Function {func.__name__} successfully executed after {retries} attempts in {count_seconds}s")
                return last_result

            self._exit_with_error_message(func.__name__)
        return wrapper

    def _sleep_with_warning_log(self, message):
        self.logger.warning(message)
        time.sleep(self.retry_wait_seconds)

    def _update_retry_timeout_seconds_from_kwargs(self, kwargs, func):
        kwargs_retry_timeout_seconds = kwargs.get('retry_timeout_seconds')
        if kwargs_retry_timeout_seconds:
            self.retry_timeout_seconds = kwargs_retry_timeout_seconds
        else:
            self.logger.debug(
                f"`retry_timeout_seconds` is not found in func {func.__name__} arguments. Using default value = {self.retry_timeout_seconds}")

    def _update_retry_wait_seconds_from_kwargs(self, kwargs, func):
        kwargs_retry_wait_seconds = kwargs.get('retry_wait_seconds')
        if kwargs_retry_wait_seconds:
            self.retry_wait_seconds = kwargs_retry_wait_seconds
        else:
            self.logger.debug(
                f"`retry_wait_seconds` is not found in func {func.__name__} arguments. Using default value = {self.retry_wait_seconds}")

    def _process_exception_during_func_execution(self, exception, count_seconds, func_name, retries, estimated_max_attempts):
        if count_seconds < self.retry_timeout_seconds:
            self._sleep_with_warning_log(
                f"Made [{retries} of {estimated_max_attempts}] retries. Exception happened during function {func_name} execution,  waiting {count_seconds} of {self.retry_timeout_seconds}. Exception: {exception}")
        else:
            self._exit_with_error_message(func_name)

    def _exit_with_error_message(self, func_name):
        self.logger.error(f"Can't execute function {func_name} in {self.retry_timeout_seconds} seconds")
        sys.exit(1)
