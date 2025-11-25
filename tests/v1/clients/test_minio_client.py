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
from datetime import datetime
from unittest.mock import patch
from minio.datatypes import Object

from qubership_pipelines_common_library.v1.minio_client import MinioClient


class TestMinioClientV1(unittest.TestCase):

    def setUp(self):
        self.bucket_name = "test-bucket"
        self.client = MinioClient("http://minio.qubership.org:9000", "user", "token")

    @patch("minio.api.Minio.list_objects")
    def test_last_modified_compares_dates(self, list_objects_mock):
        list_objects_mock.return_value = [
            Object(self.bucket_name, "test_1.yaml", last_modified=datetime(2020, 4, 20)),
            Object(self.bucket_name, "test_2.yaml", last_modified=datetime(2020, 4, 29)),
            Object(self.bucket_name, "test_3.yaml", last_modified=datetime(2020, 4, 25)),
            Object(self.bucket_name, "test_folder/", last_modified=datetime(2020, 4, 30)),
        ]
        last = self.client.get_last_modified_file(self.bucket_name)
        self.assertEqual('test_2.yaml', last.name)

    @patch("minio.api.Minio.list_objects")
    def test_file_and_folder_names_cropping(self, list_objects_mock):
        list_objects_mock.return_value = [
            Object(self.bucket_name, "tmp/files/test_1.yaml"),
            Object(self.bucket_name, "tmp/files/test_2.yaml"),
            Object(self.bucket_name, "tmp/files/test_folder1/"),
            Object(self.bucket_name, "tmp/files/test_folder2/"),
        ]
        file_names = self.client.get_file_names(self.bucket_name, "tmp/files/")
        self.assertEqual(['test_1.yaml', 'test_2.yaml'], file_names)
        dir_names = self.client.get_folder_names(self.bucket_name, "tmp/files/")
        self.assertEqual(['test_folder1', 'test_folder2'], dir_names)


if __name__ == '__main__':
    unittest.main()
