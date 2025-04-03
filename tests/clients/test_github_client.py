# Copyright 2025 NetCracker Technology Corporation
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
from qubership_pipelines_common_library.v1.github_client import GithubClient


class TestGithubClientV1(unittest.TestCase):

    def setUp(self):
        self.gh_client = GithubClient()

    @patch("github.MainClass.Github.get_repo")
    def test_get_workflow_run_status__returns_success_status(self, get_repo_mock):
        get_repo_mock().get_workflow_run().status = GithubClient.STATUS_COMPLETED
        get_repo_mock().get_workflow_run().conclusion = GithubClient.CONCLUSION_SUCCESS
        execution = ExecutionInfo().with_id("123").with_url("https://github.com/Netcracker/qubership-pipelines-common-python-library")

        self.gh_client.get_workflow_run_status(execution)

        self.assertEqual(ExecutionInfo.STATUS_SUCCESS, execution.get_status())

    @patch("github.MainClass.Github.get_repo")
    def test_get_workflow_run_status__returns_not_started_status(self, get_repo_mock):
        get_repo_mock().get_workflow_run().status = GithubClient.STATUS_PENDING
        get_repo_mock().get_workflow_run().conclusion = None
        execution = ExecutionInfo().with_id("123").with_url("https://github.com/Netcracker/qubership-pipelines-common-python-library")

        self.gh_client.get_workflow_run_status(execution)

        self.assertEqual(ExecutionInfo.STATUS_NOT_STARTED, execution.get_status())


if __name__ == '__main__':
    unittest.main()
