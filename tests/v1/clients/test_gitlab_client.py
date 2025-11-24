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
from qubership_pipelines_common_library.v1.gitlab_client import GitlabClient


class TestGitlabClientV1(unittest.TestCase):

    def setUp(self):
        self.url = "https://git.qubership.org"
        self.user = "user"
        self.token = "token"
        self.client = GitlabClient(self.url, self.user, self.token)

    @patch("gitlab.v4.objects.projects.ProjectManager.get")
    def test_get_file_decodes(self, get_project_mock):
        get_project_mock().files.get().decode.return_value = b"kind: AtlasConfig"
        result = self.client.get_file_content("1337", "main", "test.yaml")

        get_project_mock().files.get.assert_called_with(file_path="test.yaml", ref="main")
        self.assertEqual("kind: AtlasConfig", result)

    @patch("gitlab.v4.objects.projects.ProjectManager.get")
    def test_trigger_pipeline_fills_execution_params(self, get_project_mock):
        project = "quber/test"
        pipeline_id = "pipeline_1"
        pipeline_url = f"{self.url}/{project}/{pipeline_id}"
        get_project_mock().pipelines.create().web_url = pipeline_url
        get_project_mock().pipelines.create().get_id.return_value = pipeline_id

        execution = self.client.trigger_pipeline(project_id=project, pipeline_params={'ref': "main"})

        self.assertEqual(project, execution.get_name())
        self.assertEqual(pipeline_id, execution.get_id())
        self.assertEqual(pipeline_url, execution.get_url())
        self.assertEqual(ExecutionInfo.STATUS_IN_PROGRESS, execution.get_status())


    def test_get_repo_branch_path(self):
        validation_dict = {
            ("https://git.qubership.org/quber-test/quber-pipeline/-/blob/main/response_data/file.json", "main"):
                ("https://git.qubership.org/quber-test/quber-pipeline", "main", "response_data/file.json"),
            ("https://git.qubership.org/quber-test/quber-pipeline/-/raw/main/response_data", "main"):
                ("https://git.qubership.org/quber-test/quber-pipeline", "main", "response_data"),
            ("https://git.qubership.org/quber-test/quber-pipeline/-/tree/feature/with_slash/response_data/file.json", "feature/with_slash"):
                ("https://git.qubership.org/quber-test/quber-pipeline", "feature/with_slash", "response_data/file.json"),
        }
        for args, output in validation_dict.items():
            self.assertEqual(self.client.get_repo_branch_path(args[0], branch=args[1]),
                             {
                                 "repo": output[0],
                                 "branch": output[1],
                                 "path": output[2],
                             })



if __name__ == '__main__':
    unittest.main()
