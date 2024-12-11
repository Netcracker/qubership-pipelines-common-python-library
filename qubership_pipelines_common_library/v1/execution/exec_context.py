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

import os, logging

from pathlib import Path
from v1.utils.utils_file import UtilsFile
from .exec_context_file import ExecutionContextFile
from .exec_logger import ExecutionLogger


class ExecutionContext:

    def __init__(self, context_path: str):
        full_path = os.path.abspath(context_path)
        self.context_path = full_path
        self.context = ExecutionContextFile(full_path)
        # init primary folders for logs and temporary files
        self.input_params = ExecutionContextFile().init_params()
        self.input_params_secure = ExecutionContextFile().init_params_secure()
        self.output_params = ExecutionContextFile().init_params()
        self.output_params_secure = ExecutionContextFile().init_params_secure()
        self.__init_temp_folder()
        self.__init_logger()
        # load context from files
        logging.info(f"""Execution context params:
            paths.logs: {self.context.get("paths.logs")}
            paths.temp: {self.context.get("paths.temp")}
            paths.input.params: {self.context.get("paths.input.params")}
            paths.input.params_secure: {self.context.get("paths.input.params_secure")}
            paths.input.files: {self.context.get("paths.input.files")}
            paths.output.params: {self.context.get("paths.output.params")}
            paths.output.params_secure: {self.context.get("paths.output.params_secure")}
            paths.output.files: {self.context.get("paths.output.files")}
        """)
        self.__input_params_load()

    def output_params_save(self):
        if self.context.get("paths.output.params"):
            logging.info(f"Writing insecure param file '{self.context.get('paths.output.params')}'")
            self.output_params.save(self.context.get("paths.output.params"))
        if self.context.get("paths.output.params_secure"):
            logging.info(f"Writing secure param file '{self.context.get('paths.output.params_secure')}'")
            self.output_params_secure.save(self.context.get("paths.output.params_secure"))

    def input_param_get(self, path, def_value=None):
        value = self.input_params.get(path, def_value)
        if value == def_value:
            value = self.input_params_secure.get(path, def_value)
            if value == def_value:
                value = self.context.get(path, def_value)
        return value

    def output_param_set(self, path, value):
        return self.output_params.set(path, value)

    def output_param_secure_set(self, path, value):
        return self.output_params_secure.set(path, value)

    def validate(self, names, silent=False):
        valid = True
        for key in names:
            if not self.__validate_param(key):
                valid = False
                if not silent:
                    logging.error(f"Parameter '{key}' is mandatory but not defined")
        return valid

    def __validate_param(self, name):
        try:
            return self.context.get(name) or self.input_param_get(name)  # or self.__dict__.get(name)
        except:
            return False

    def __input_params_load(self):
        if self.context.get("paths.input.params"):
            self.input_params = ExecutionContextFile(self.context.get("paths.input.params"))
        if self.context.get("paths.input.params_secure"):
            self.input_params_secure = ExecutionContextFile(self.context.get("paths.input.params_secure"))

    def __init_temp_folder(self):
        # get temp path either from context variable or calculate path to temp folder using context_path value
        if self.context.get("paths.temp"):
            self.path_temp = Path(self.context.get("paths.temp"))
        else:
            self.path_temp = Path(os.path.dirname(self.context_path)).joinpath("temp").resolve()
            self.context.set("paths.temp", self.path_temp)
        if self.path_temp.exists():
            UtilsFile.rmtree(self.path_temp)
        self.path_temp.mkdir(parents=True, exist_ok=True)

    def __init_logger(self):
        # get logs path either from context variable or calculate path to logs folder using context_path value
        if self.context.get("paths.logs"):
            self.path_logs = Path(self.context.get("paths.logs"))
        else:
            self.path_logs = Path(os.path.dirname(self.context_path)).joinpath("logs").resolve()
            self.context.set("paths.logs", self.path_logs)
        if self.path_logs.exists():
            UtilsFile.rmtree(self.path_logs)
        self.path_logs.mkdir(parents=True, exist_ok=True)
        self.logger = ExecutionLogger(self.path_logs)
