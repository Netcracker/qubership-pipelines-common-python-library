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
from kubernetes.client import V1DeploymentStatus, V1ObjectMeta, V1Deployment
from qubership_pipelines_common_library.v1.kube_client import KubeClient, ResourceReplicaCount, ResourceKind


class TestKubeClientV1(unittest.TestCase):

    def setUp(self):
        self.client = KubeClient("http://kube.qubership.org:6443", "token")

    @patch("qubership_pipelines_common_library.v1.kube_client.KubeClient._KubeClient__get_deployments_and_stateful_sets")
    def test_list_not_ready_resources(self, get_deps_and_ss_mock):
        get_deps_and_ss_mock.return_value = [
            self.__create_deployment_with_status("test_dep1", 3, 3),
            self.__create_deployment_with_status("test_dep2", 0, 1),
            self.__create_deployment_with_status("test_dep3", 2, 2),
            self.__create_deployment_with_status("test_dep4", 1, 2),
        ]
        not_ready_resources = self.client.list_not_ready_resources("test-namespace")
        self.assertEqual([ResourceReplicaCount("test_dep2", ResourceKind.DEPLOYMENT, 0, 1),
                          ResourceReplicaCount("test_dep4", ResourceKind.DEPLOYMENT, 1, 2)], not_ready_resources)

    def __create_deployment_with_status(self, name, available_replicas, target_replicas):
        return V1Deployment(status=V1DeploymentStatus(available_replicas=available_replicas, replicas=target_replicas),
                            metadata=V1ObjectMeta(name=name))


if __name__ == '__main__':
    unittest.main()
