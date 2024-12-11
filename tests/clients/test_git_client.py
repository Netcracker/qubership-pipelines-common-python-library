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

import unittest
from unittest.mock import patch

from qubership_pipelines_common_library.v1.git_client import GitClient


class TestGitClientV1(unittest.TestCase):

    def setUp(self):
        self.url = "http://git.qubership.org"
        self.user = "user"
        self.token = "token"
        self.email = "test@qs.org"
        self.client = GitClient(self.url, self.user, self.token, self.email)

    @patch("gitlab.v4.objects.projects.ProjectManager.get")
    def test_get_file_decodes(self, get_project_mock):
        get_project_mock().files.get().decode.return_value = b"kind: AtlasConfig"
        result = self.client.get_file_content("1337", "main", "test.yaml")

        get_project_mock().files.get.assert_called_with(file_path="test.yaml", ref="main")
        self.assertEqual("kind: AtlasConfig", result)


if __name__ == '__main__':
    unittest.main()
