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
import pytest

from qubership_pipelines_common_library.v1.minio_client import MinioClient


@pytest.mark.integration
class TestMinioIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # static IP used in workflow
        cls.client = MinioClient("http://127.0.0.1:9000", "admin", "admin123")
        cls.bucket_name = "integration-test-bucket"

    def test_bucket_exists(self):
        exists = TestMinioIntegration.client.minio.bucket_exists(TestMinioIntegration.bucket_name)
        self.assertEqual(exists, True)

    def test_bucket_is_empty(self):
        self.assertEqual(TestMinioIntegration.client.list_objects(TestMinioIntegration.bucket_name, ""), [])


if __name__ == '__main__':
    unittest.main()
