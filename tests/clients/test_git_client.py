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
        self.url = "https://git.qubership.org"
        self.user = "user"
        self.token = "token"
        self.client = GitClient(self.url, self.user, self.token)

    @patch("git.repo.base.Repo.clone_from")
    def test_clone_generates_correct_repo_url(self, clone_repo_mock):
        temp_path = "temp/repo_temp_dir"
        branch = "main"
        self.client.clone("quber/tests", branch, temp_path, depth=1)
        clone_repo_mock.assert_called_with(f"https://{self.user}:{self.token}@git.qubership.org/quber/tests", temp_path, branch=branch, depth=1)


if __name__ == '__main__':
    unittest.main()
