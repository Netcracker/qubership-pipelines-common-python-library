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

from qubership_pipelines_common_library.v1.execution.exec_context import ExecutionContext
from qubership_pipelines_common_library.v1.utils.utils_context import create_execution_context


class ExecutionCommand:

    SUCCESS_MSG = "Status: SUCCESS"
    FAILURE_MSG = "Status: FAILURE"

    def __init__(self, context_path: str = None, input_params: dict = None, input_params_secure: dict = None,
                 folder_path: str = None, parent_context_to_reuse: ExecutionContext = None):
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
        """
        if not context_path:
            context_path = create_execution_context(input_params=input_params, input_params_secure=input_params_secure,
                                                    folder_path=folder_path, parent_context_to_reuse=parent_context_to_reuse)
        self.context = ExecutionContext(context_path)

    def run(self):
        """Runs command following its lifecycle"""
        try:
            if not self._validate():
                logging.error(ExecutionCommand.FAILURE_MSG)
                self._exit(False, ExecutionCommand.FAILURE_MSG)
            self._execute()
            self._exit(True, ExecutionCommand.SUCCESS_MSG)
        except Exception as e:
            logging.error(traceback.format_exc())
            self._exit(False, ExecutionCommand.FAILURE_MSG)

    def _validate(self):
        return self.context.validate(["paths.input.params"])

    def _execute(self):
        logging.info("Status: SKIPPED")

    def _exit(self, success: bool, message: str):
        if success:
            self.context.logger.info(message)
            sys.exit(0)
        else:
            self.context.logger.error(message)
            sys.exit(1)
