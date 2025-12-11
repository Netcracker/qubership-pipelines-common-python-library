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
from unittest.mock import patch, MagicMock
from qubership_pipelines_common_library.v1.execution.exec_info import ExecutionInfo
from qubership_pipelines_common_library.v2.github.github_client import GithubClient


class TestGithubClientV2(unittest.TestCase):

    def setUp(self):
        self.gh_client = GithubClient(token="test_token")

    @patch("ghapi.core.GhApi.__call__")
    def test_get_workflow_run_status__returns_success_status(self, get_workflow_run_mock):
        get_workflow_run_mock().status = GithubClient.STATUS_COMPLETED
        get_workflow_run_mock().conclusion = GithubClient.CONCLUSION_SUCCESS
        execution = ExecutionInfo().with_id("123").with_url("https://github.com/Netcracker/qubership-pipelines-common-python-library")

        self.gh_client.get_workflow_run_status(execution)

        self.assertEqual(ExecutionInfo.STATUS_SUCCESS, execution.get_status())

    @patch("ghapi.core.GhApi.__call__")
    def test_get_workflow_run_status__returns_not_started_status(self, get_workflow_run_mock):
        get_workflow_run_mock().status = GithubClient.STATUS_PENDING
        get_workflow_run_mock().conclusion = None
        execution = ExecutionInfo().with_id("123").with_url("https://github.com/Netcracker/qubership-pipelines-common-python-library")

        self.gh_client.get_workflow_run_status(execution)

        self.assertEqual(ExecutionInfo.STATUS_NOT_STARTED, execution.get_status())

    @patch("ghapi.core.GhApi.__call__")
    def test_get_workflow_run_input_params__returns_params(self, ghapi_mock):
        artifact_mock = MagicMock()
        artifact_mock.name = GithubClient.DEFAULT_UUID_ARTIFACT_NAME
        artifacts_mock = MagicMock()
        artifacts_mock.artifacts = [artifact_mock]
        ghapi_mock.return_value = artifacts_mock
        self.gh_client._save_artifact_to_dir = MagicMock(return_value = f"./tests/v1/data/{GithubClient.DEFAULT_UUID_ARTIFACT_NAME}.zip")

        params = self.gh_client.get_workflow_run_input_params(ghapi_mock)

        self.assertEqual({"test_input_param": "123", "workflow_run_uuid": "e0228fab-6be5-46c4-9024-3ddc3e229b41"}, params)


if __name__ == '__main__':
    unittest.main()
