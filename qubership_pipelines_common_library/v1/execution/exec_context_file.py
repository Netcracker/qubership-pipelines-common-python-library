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

from v1.utils.utils_file import UtilsFile
from v1.utils.utils_dictionary import UtilsDictionary


class ExecutionContextFile:
    KIND_CONTEXT_DESCRIPTOR = "AtlasModuleContextDescriptor"
    KIND_PARAMS_INSECURE = "AtlasModuleParamsInsecure"
    KIND_PARAMS_SECURE = "AtlasModuleParamsSecure"
    SUPPORTED_KINDS = [KIND_CONTEXT_DESCRIPTOR, KIND_PARAMS_INSECURE, KIND_PARAMS_SECURE]

    API_VERSION_V1 = "v1"
    SUPPORTED_API_VERSIONS = [API_VERSION_V1]

    def __init__(self, path=None):
        self.content = {
            "kind": "",
            "apiVersion": ""
        }
        self.path = path
        if path:
            self.load(path)

    def init_empty(self):
        self.content = {
            "kind": "",
            "apiVersion": ""
        }

    def init_context_descriptor(self):
        self.content = {
            "kind": ExecutionContextFile.KIND_CONTEXT_DESCRIPTOR,
            "apiVersion": ExecutionContextFile.API_VERSION_V1,
            "paths": {
                # "logs": "" - optional full path to folder with logs
                # "temp": "" - optional full path to folder with temporary files
                "input": {
                    "params": "",         # full path to file with input execution parameters (non encrypted)
                    "params_secure": "",  # full path to file with input execution parameters (encrypted)
                    "files": ""           # full path to the folder with input files
                },
                "output": {
                    "params": "",         # path to a file, to which CLI should write output parameters (non encrypted).
                                          # these parameters will be included to context
                    "params_secure": "",  # path to a file, to which CLI should write output parameters (encrypted).
                                          # these parameters will be included to context
                    "files": ""           # path to folder, to which CLI should write output files.
                                          # these files will be included to context
                }
            }
        }
        return self

    def init_params(self):
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
        except FileNotFoundError as e:
            self.init_empty()

    def save(self, path):
        # TODO: support encryption with SOPS
        UtilsFile.write_yaml(path, self.content)

    def get(self, path, def_value=None):
        return UtilsDictionary.get_by_path(self.content, path, def_value)

    def set(self, path, value):
        UtilsDictionary.set_by_path(self.content, path, value)
        return self

    def set_multiple(self, dict):
        for key in dict:
            UtilsDictionary.set_by_path(self.content, key, dict[key])
        return self
