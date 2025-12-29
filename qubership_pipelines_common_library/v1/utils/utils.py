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

from qubership_pipelines_common_library.v1.utils.utils_file import UtilsFile


def parse_system_params(context_path: str, system: str):
   result = dict()
   context_yaml = UtilsFile.read_yaml(context_path)
   result["url"] = context_yaml["systems"][system]["url"]
   result["username"] = context_yaml["systems"][system]["username"]
   result["password"] = context_yaml["systems"][system]["password"]
   return result


def fill_param_by_type(json_data, param_name, new_value, clear_current_value=False):
   current_value = json_data.get(param_name)
   if isinstance(current_value, list):
      if clear_current_value:
         json_data[param_name] = new_value if isinstance(new_value, list) else [new_value]
      else:
         if isinstance(new_value, list):
            current_value.extend(new_value)
         else:
            current_value.append(new_value)
   else:
      json_data[param_name] = new_value
   return json_data


def recursive_merge(source: dict, target: dict):
   if target is None:
      return source
   for key, value in target.items():
      if key in source and isinstance(source[key], dict) and isinstance(value, dict):
         source[key] = recursive_merge(source[key], value)
      else:
         source[key] = value
   return source
