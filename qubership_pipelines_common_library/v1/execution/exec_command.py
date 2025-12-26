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
import sys
import traceback
from abc import ABC, abstractmethod

from qubership_pipelines_common_library.v1.execution.exec_context import ExecutionContext
from qubership_pipelines_common_library.v1.utils.utils_context import create_execution_context
from qubership_pipelines_common_library.v2.utils.crypto_utils import CryptoUtils


class ExecutionCommand:

    SUCCESS_MSG = "Status: SUCCESS"
    FAILURE_MSG = "Status: FAILURE"

    def __init__(self, context_path: str = None, input_params: dict = None, input_params_secure: dict = None,
                 folder_path: str = None, parent_context_to_reuse: ExecutionContext = None,
                 pre_execute_actions: list['ExecutionCommandExtension'] = None,
                 post_execute_actions: list['ExecutionCommandExtension'] = None):
        """
        Extendable interface intended to simplify working with input/output params and passing them between commands in different Pipeline Executors

        Implementations are expected to override **`_validate`** and **`_execute`** methods

        If **`context_path`** is not provided - context will be created dynamically using other provided params

        Arguments:
            context_path (str): Path to context-describing yaml, that should contain references to input/output param file locations
            input_params (dict): Non-secure parameters that will be merged into dynamically created params
            input_params_secure (dict): Secure parameters that will be merged into dynamically created params
            folder_path (str): Folder path where dynamically-created context will be stored. Optional, will create new temp folder if missing.
            parent_context_to_reuse (ExecutionContext): Optional, existing context to propagate input params from.
            pre_execute_actions: Optional, list of actions, implementing ExecutionCommandExtension, to be executed before command
            post_execute_actions: Optional, list of actions, implementing ExecutionCommandExtension, to be executed after command
        """
        if not context_path:
            context_path = create_execution_context(input_params=input_params, input_params_secure=input_params_secure,
                                                    folder_path=folder_path, parent_context_to_reuse=parent_context_to_reuse)
        self.context = ExecutionContext(context_path)
        self._pre_execute_actions = []
        if pre_execute_actions:
            self._pre_execute_actions.extend(pre_execute_actions)
        self._post_execute_actions = []
        if post_execute_actions:
            self._post_execute_actions.extend(post_execute_actions)

    def run(self):
        """Runs command following its lifecycle"""
        try:
            self._log_command_class_name()
            self._log_border_line()
            self._log_input_params()
            if not self._validate():
                logging.error(ExecutionCommand.FAILURE_MSG)
                self._exit(False, ExecutionCommand.FAILURE_MSG)
            self._pre_execute()
            self._execute()
            self._post_execute()
            self._exit(True, ExecutionCommand.SUCCESS_MSG)
        except Exception:
            logging.error(traceback.format_exc())
            self._exit(False, ExecutionCommand.FAILURE_MSG)
        finally:
            self._log_border_line()

    def _log_command_class_name(self):
        self.context.logger.info("command_class_name = %s", type(self).__name__)

    def _log_border_line(self):
        self.context.logger.info("=" * 60)

    def _log_input_params(self):
        self.context.logger.info(
            "Input context parameters:\n%s\n%s",
            CryptoUtils.get_parameters_for_print(self.context.input_params_secure.content, True),
            CryptoUtils.get_parameters_for_print(self.context.input_params.content, False)
        )

    def _validate(self):
        return self.context.validate(["paths.input.params"])

    def _pre_execute(self):
        for action in self._pre_execute_actions:
            action.with_command(self).execute()

    def _execute(self):
        logging.info("Status: SKIPPED")

    def _post_execute(self):
        for action in self._post_execute_actions:
            action.with_command(self).execute()

    def _exit(self, success: bool, message: str):
        if success:
            self.context.logger.info(message)
            sys.exit(0)
        else:
            self.context.logger.error(message)
            sys.exit(1)


class ExecutionCommandExtension(ABC):
    """
    Base interface used in ExecutionCommand pre_execute and post_execute actions
    Can be extended by users to perform custom extension logic before and after execution
    """

    def __init__(self):
        self.context = None
        self.command = None

    def with_command(self, command: ExecutionCommand) -> 'ExecutionCommandExtension':
        self.command = command
        self.context = command.context
        return self

    @abstractmethod
    def execute(self) -> None:
        """Implements custom extension logic"""
        pass
