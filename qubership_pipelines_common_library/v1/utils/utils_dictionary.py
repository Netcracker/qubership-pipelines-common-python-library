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


class UtilsDictionary:

    @staticmethod
    def get_by_path(input_dict, path, def_value):
        if isinstance(path, str):
            path = path.split(".")
        curr = input_dict
        for key in path:
            if key not in curr:
                return def_value
            curr = curr[key]
        return curr

    @staticmethod
    def set_by_path(input_dict, path, value):
        if isinstance(path, str):
            path = path.split(".")
        curr = input_dict
        index = -1
        for key in path:
            index += 1
            if index == len(path) - 1:
                curr[key] = value
            elif key not in curr:
                curr[key] = {}
            curr = curr[key]
        return input_dict