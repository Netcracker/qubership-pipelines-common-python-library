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

import os, pathlib, yaml, shutil

from pathlib import Path


class UtilsFile:

    @staticmethod
    def read_yaml(filepath):
        with open(filepath, 'r', encoding='utf-8') as file:
            return yaml.safe_load(file)

    @staticmethod
    def write_yaml(filepath, content):
        directory = os.path.dirname(filepath)
        if directory:
            pathlib.Path(directory).mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as stream:
            yaml.safe_dump(content, stream, default_flow_style=False, sort_keys=False)

    @staticmethod
    def read_text_utf8(filepath):
        return Path(filepath).read_text(encoding='utf-8')

    @staticmethod
    def write_text_utf8(filepath, content):
        directory = os.path.dirname(filepath)
        if directory:
            pathlib.Path(directory).mkdir(parents=True, exist_ok=True)
        Path(filepath).write_text(content, encoding='utf-8')

    @staticmethod
    def rmtree(path):
        shutil.rmtree(path, onerror=UtilsFile._onerror_rmtree)

    @staticmethod
    def _onerror_rmtree(func, path, exc_info):
        """
        Error handler for ``shutil.rmtree``.

        If the error is due to an access error (read only file)
        it attempts to add write permission and then retries.

        If the error is for another reason it re-raises the error.

        Usage : ``shutil.rmtree(path, onerror=onerror)``
        """
        import stat
        # Is the error an access error?
        if not os.access(path, os.W_OK):
            os.chmod(path, stat.S_IWUSR)
            func(path)
        else:
            raise
