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

from qubership_pipelines_common_library.v1.execution.exec_info import ExecutionInfo
from qubership_pipelines_common_library.v1.jenkins_client import JenkinsClient


class TestJenkinsClientV1(unittest.TestCase):

    def setUp(self):
        self.url = "http://jenkins.qubership.org"
        self.user = "user"
        self.token = "token"

    @patch("jenkins.Jenkins")
    def test_get_file_decodes(self, server_mock):
        client = JenkinsClient(self.url, self.user, self.token)
        exec_info = client.run_pipeline("test_job", {})
        self.assertEqual(ExecutionInfo.STATUS_IN_PROGRESS, exec_info.status)


if __name__ == '__main__':
    unittest.main()
