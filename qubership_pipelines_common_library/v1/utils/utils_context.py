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
import tempfile
from datetime import datetime
from pathlib import Path

from qubership_pipelines_common_library.v1.execution.exec_context import ExecutionContext
from qubership_pipelines_common_library.v1.execution.exec_context_file import ExecutionContextFile
from qubership_pipelines_common_library.v1.utils.utils import recursive_merge
from qubership_pipelines_common_library.v1.utils.utils_file import UtilsFile


def init_context(context_path):
    context = {
        'meta': {
            'created_when': datetime.now(),
            'type': 'ContextFile'
        },
        'systems': {

        },
        'params': {
        }
    }
    UtilsFile.write_yaml(context_path, context)


def create_execution_context(input_params: dict = None, input_params_secure: dict = None, folder_path: str = None,
                             parent_context_to_reuse: ExecutionContext = None):
    """
    Dynamically creates **`ExecutionContext`** using provided params.

    Arguments:
        input_params: dict (will be merged into created input params)
        input_params_secure: dict (will be merged into created secure input params)
        folder_path: str (optional, will generate new temp)
        parent_context_to_reuse: ExecutionContext (optional, to propagate existing input params)
    """

    # Create workdir and save its path
    if folder_path:
        resolved_path = Path(folder_path).resolve()
        if resolved_path.exists():
            UtilsFile.rmtree(resolved_path)
        resolved_path.mkdir(parents=True, exist_ok=True)
    else:
        folder_path = tempfile.mkdtemp()

    # Init default files and folders structure
    context_file = ExecutionContextFile().init_context_descriptor(context_folder_path=folder_path)
    context_path = Path(folder_path).joinpath("context.yaml")
    context_file.save(context_path)

    # Init param files by merging defaults with optional input dict and previous context params, and save them
    input_params_file = ExecutionContextFile()
    input_params_secure_file = ExecutionContextFile()
    if parent_context_to_reuse:
        input_params_file.content = parent_context_to_reuse.input_params.content
        input_params_secure_file.content = parent_context_to_reuse.input_params_secure.content
    else:
        input_params_file.init_params()
        input_params_secure_file.init_params_secure()

    input_params_file.content = recursive_merge(input_params_file.content, input_params)
    input_params_file.save(context_file.get("paths.input.params"))
    input_params_secure_file.content = recursive_merge(input_params_secure_file.content, input_params_secure)
    input_params_secure_file.save(context_file.get("paths.input.params_secure"))

    ExecutionContextFile().init_params().save(context_file.get("paths.output.params"))
    ExecutionContextFile().init_params_secure().save(context_file.get("paths.output.params_secure"))
    Path(context_file.get("paths.input.files")).mkdir(parents=True, exist_ok=True)
    Path(context_file.get("paths.output.files")).mkdir(parents=True, exist_ok=True)

    logging.debug(f"Created context at {context_path}")
    return context_path
