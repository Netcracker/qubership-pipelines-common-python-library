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

import logging, os
from pathlib import Path

from qubership_pipelines_common_library.v1.utils.utils_file import UtilsFile
from qubership_pipelines_common_library.v1.utils.utils_dictionary import UtilsDictionary


class ExecutionContextFile:
    KIND_CONTEXT_DESCRIPTOR = "AtlasModuleContextDescriptor"
    KIND_PARAMS_INSECURE = "AtlasModuleParamsInsecure"
    KIND_PARAMS_SECURE = "AtlasModuleParamsSecure"
    SUPPORTED_KINDS = [KIND_CONTEXT_DESCRIPTOR, KIND_PARAMS_INSECURE, KIND_PARAMS_SECURE]

    INPUT_FOLDER_NAME = "input"
    OUTPUT_FOLDER_NAME = "output"
    FILES_FOLDER_NAME = "files"
    PARAMS_FILE_NAME = "params.yaml"
    PARAMS_SECURE_FILE_NAME = "params_secure.yaml"

    API_VERSION_V1 = "v1"
    SUPPORTED_API_VERSIONS = [API_VERSION_V1]

    def __init__(self, path=None):
        """
        Interface to work with **`params`** and **`context`** files, used in **`ExecutionContext`**.

        Provides methods to init default content for different types of descriptors (e.g. **`init_context_descriptor`**, **`init_params`**)
        """
        self.content = {
            "kind": "",
            "apiVersion": ""
        }
        self.path = path
        if path:
            self.load(path)

    def init_empty(self):
        """"""
        self.content = {
            "kind": "",
            "apiVersion": ""
        }

    def init_context_descriptor(self, context_folder_path: str = None):
        """"""
        if context_folder_path is None:
            context_folder_path = ""
        ctx_path = Path(context_folder_path)
        self.content = {
            "kind": ExecutionContextFile.KIND_CONTEXT_DESCRIPTOR,
            "apiVersion": ExecutionContextFile.API_VERSION_V1,
            "paths": {
                "input": {
                    "params": ctx_path.joinpath(ExecutionContextFile.INPUT_FOLDER_NAME,
                                                ExecutionContextFile.PARAMS_FILE_NAME).as_posix(),
                    # full path to file with input execution parameters (non encrypted)
                    "params_secure": ctx_path.joinpath(ExecutionContextFile.INPUT_FOLDER_NAME,
                                                       ExecutionContextFile.PARAMS_SECURE_FILE_NAME).as_posix(),
                    # full path to file with input execution parameters (encrypted)
                    "files": ctx_path.joinpath(ExecutionContextFile.INPUT_FOLDER_NAME,
                                               ExecutionContextFile.FILES_FOLDER_NAME).as_posix()
                    # full path to the folder with input files
                },
                "output": {
                    "params": ctx_path.joinpath(ExecutionContextFile.OUTPUT_FOLDER_NAME,
                                                ExecutionContextFile.PARAMS_FILE_NAME).as_posix(),
                    # path to a file, to which CLI should write output parameters (non encrypted).
                    # these parameters will be included to context
                    "params_secure": ctx_path.joinpath(ExecutionContextFile.OUTPUT_FOLDER_NAME,
                                                       ExecutionContextFile.PARAMS_SECURE_FILE_NAME).as_posix(),
                    # path to a file, to which CLI should write output parameters (encrypted).
                    # these parameters will be included to context
                    "files": ctx_path.joinpath(ExecutionContextFile.OUTPUT_FOLDER_NAME,
                                               ExecutionContextFile.FILES_FOLDER_NAME).as_posix(),
                    # path to folder, to which CLI should write output files.
                    # these files will be included to context
                }
            }
        }
        return self

    def init_params(self):
        """"""
        self.content = {
            "kind": ExecutionContextFile.KIND_PARAMS_INSECURE,
            "apiVersion": ExecutionContextFile.API_VERSION_V1,
            "params": {},  # there should be "key": "value" pairs without interpolation
            "files": {},   # there should be "key": "file_name" pairs that describes input/output files
            "systems": {
                # "jenkins": {
                #     "url": "",
                #     "username": "",
                #     "password": ""
                # }
            }
        }
        return self

    def init_params_secure(self):
        """"""
        self.content = {
            "kind": ExecutionContextFile.KIND_PARAMS_SECURE,
            "apiVersion": ExecutionContextFile.API_VERSION_V1,
            "params": {},  # there should be "key": "value" pairs without interpolation
            "files": {},   # there should be "key": "file_name" pairs that describes input/output files
            "systems": {
                # "jenkins": {
                #     "url": "",
                #     "username": "",
                #     "password": ""
                # }
            }
        }
        return self

    def load(self, path):
        """Loads and validates file as one of supported types of descriptors"""
        full_path = os.path.abspath(path)
        try:
            self.content = UtilsFile.read_yaml(full_path)
            # validate supported kinds and versions
            if self.content["kind"] not in ExecutionContextFile.SUPPORTED_KINDS:
                logging.error(f"Incorrect kind value: {self.content['kind']} in file '{full_path}'. "
                              f"Only '{ExecutionContextFile.SUPPORTED_KINDS}' are supported")
                self.init_empty()
            if self.content["apiVersion"] not in ExecutionContextFile.SUPPORTED_API_VERSIONS:
                logging.error(f"Incorrect apiVersion value: {self.content['apiVersion']} in file '{full_path}'. "
                              f"Only '{ExecutionContextFile.SUPPORTED_API_VERSIONS}' are supported")
                self.init_empty()
        except FileNotFoundError:
            self.init_empty()

    def save(self, path):
        """Writes current file content from memory to disk"""
        # TODO: support encryption with SOPS
        UtilsFile.write_yaml(path, self.content)

    def get(self, path, def_value=None):
        """Gets parameter from current file content by its param path, supporting dot-separated nested keys (e.g. 'parent_obj.child_obj.param_name')"""
        return UtilsDictionary.get_by_path(self.content, path, def_value)

    def set(self, path, value):
        """Sets parameter in current file content"""
        UtilsDictionary.set_by_path(self.content, path, value)
        return self

    def set_multiple(self, dict):
        """Sets multiple parameters in current file content"""
        for key in dict:
            UtilsDictionary.set_by_path(self.content, key, dict[key])
        return self
