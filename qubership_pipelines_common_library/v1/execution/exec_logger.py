# Copyright 2024 NetCracker Technology Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import os


class ExecutionLogger:
    FILE_NAME_EXECUTION = "execution.log"
    FILE_NAME_FULL = "full.log"
    EXECUTION_LOG_LEVEL = logging.INFO
    FULL_LOG_LEVEL = logging.DEBUG
    DEFAULT_FORMAT = u'[%(asctime)s] [%(levelname)-7s] [class=%(filename)s:%(lineno)-3s] %(message)s'
    LEVELNAME_COLORED_FORMAT = u'[%(asctime)s] [%(levelname_color_open_tag)s%(levelname)-7s%(levelname_color_close_tag)s] \\[class=%(filename)s:%(lineno)-3s] %(message)s'

    def __init__(self, path_logs):
        """
        Default logger used by **`ExecutionCommands`**, implicitly initialized when using Context.

        Reference to it is available from instance of **`ExecutionContext`**.

        Provides common logging methods of different log levels - e.g. **`debug`**, **`info`**, **`error`**
        """
        # todo: Currently all commands (if more than one are invoked in one go) will reuse same logger
        #  Also, file handlers are never removed
        self.path_logs = path_logs
        self.logger = logging.getLogger("execution_logger")
        self.logger.setLevel(logging.DEBUG)  # set to the lowest level to allow handlers to capture anything
        self.logger.propagate = True

        if path_logs:
            # execution logs - only in local logger
            handler_exec = logging.FileHandler(os.path.join(path_logs, ExecutionLogger.FILE_NAME_EXECUTION))
            handler_exec.setLevel(ExecutionLogger.EXECUTION_LOG_LEVEL)
            handler_exec.setFormatter(logging.Formatter(ExecutionLogger.DEFAULT_FORMAT))
            self.logger.addHandler(handler_exec)

            # full logs - attach to a global logger
            handler_full = logging.FileHandler(os.path.join(path_logs, ExecutionLogger.FILE_NAME_FULL))
            handler_full.setLevel(ExecutionLogger.FULL_LOG_LEVEL)
            handler_full.setFormatter(logging.Formatter(ExecutionLogger.DEFAULT_FORMAT))
            logging.getLogger().addHandler(handler_full)

    def info(self, msg, *args, **kwargs):
        self.logger.info(msg, *args, **kwargs)

    def debug(self, msg, *args, **kwargs):
        self.logger.debug(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self.logger.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self.logger.error(msg, *args, **kwargs)

    def exception(self, msg, *args, **kwargs):
        self.logger.exception(msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        self.logger.critical(msg, *args, **kwargs)

    def fatal(self, msg, *args, **kwargs):
        self.logger.fatal(msg, *args, **kwargs)
