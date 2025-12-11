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

import json
import os
import unittest
import pytest

from qubership_pipelines_common_library.v1.execution.exec_info import ExecutionInfo
from qubership_pipelines_common_library.v2.gitlab.gitlab_client import GitlabClient


@pytest.mark.integration
class TestGitlabIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.host = "https://gitlab.com"
        cls.token = os.getenv('GITLAB_QUBER_TOKEN', "UNKNOWN")
        cls.client = GitlabClient(cls.host, username=None, password=cls.token)
        cls.project_id = "quber-test/quber-pipeline"
        cls.ref = "tests"

    def test_get_file(self):
        test_file_content = TestGitlabIntegration.client.get_file_content(TestGitlabIntegration.project_id,
                                                                          TestGitlabIntegration.ref,
                                                                          "response_data/response.json")
        self.assertEqual(42, json.loads(test_file_content)["answer"])

    def test_create_and_wait_pipeline(self):
        execution = TestGitlabIntegration.client.create_pipeline(TestGitlabIntegration.project_id,
                                                                 ref=TestGitlabIntegration.ref,
                                                                 variables={})
        execution = TestGitlabIntegration.client.wait_pipeline_execution(
            execution=execution,
            timeout_seconds=60,
            wait_seconds=5,
        )
        self.assertEqual(ExecutionInfo.STATUS_SUCCESS, execution.get_status())

    def test_project_exists(self):
        result = GitlabClient.is_gitlab_project_exist(
            TestGitlabIntegration.host, TestGitlabIntegration.project_id, TestGitlabIntegration.token
        )
        self.assertTrue(result)

    def test_search_group_id(self):
        group_id = GitlabClient.search_group_id(
            TestGitlabIntegration.host, "quber-test", TestGitlabIntegration.token
        )
        self.assertEqual(group_id, 101373774)


if __name__ == '__main__':
    unittest.main()
