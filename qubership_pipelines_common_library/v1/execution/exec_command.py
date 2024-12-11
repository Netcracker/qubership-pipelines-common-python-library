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
import traceback

from .exec_context import ExecutionContext

class ExecutionCommand:

    def __init__(self, context_path):
        self.context = ExecutionContext(context_path)

    def run(self):
        try:
            if not self._validate():
                logging.error("Status: FAILURE")
                return False
            self._execute()
        except Exception as e:
            logging.error(traceback.format_exc())

    def _validate(self):
        return self.context.validate(["paths.input.params"])

    def _execute(self):
        logging.info(f"Status: SKIPPED")