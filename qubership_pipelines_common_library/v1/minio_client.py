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

import logging
from minio import Minio
from minio.datatypes import Object


class MinioClient:
    def __init__(self, endpoint: str, access_key: str, secret_key: str, secure: bool = True, cert_check: bool = True):
        if "://" in endpoint:
            ep_parts = endpoint.split("://", 2)
            secure = True if ep_parts[0] == "https" else False
            endpoint = ep_parts[1]
        self.minio = Minio(endpoint, access_key, secret_key, secure=secure, cert_check=cert_check)
        logging.info("Minio Client configured for %s", endpoint)

    def list_objects(self, bucket_name: str, path: str = None):
        """ No leading slash in 'path' - newer versions of MiniO don't support it,
            Trailing slash in 'path' must be present
            e.g. don't do this: path="/folder1/folder2"
                       do this: path="folder/folder2/"
        """
        return [MinioObject(obj) for obj in self.minio.list_objects(bucket_name, path)]

    def get_folder_names(self, bucket_name: str, path: str = None):
        return [obj.name for obj in self.list_objects(bucket_name, path) if obj.is_dir]

    def get_file_names(self, bucket_name: str, path: str = None):
        return [obj.name for obj in self.list_objects(bucket_name, path) if not obj.is_dir]

    def get_last_modified_file(self, bucket_name: str, path: str = None):
        files = [obj for obj in self.list_objects(bucket_name, path) if not obj.is_dir]
        return max(files, key=lambda f: f.last_modified) if files else None

    def get_last_modified_text_file_content(self, bucket_name: str, path: str = None):
        file = self.get_last_modified_file(bucket_name, path)
        return self.get_text_file_content(bucket_name, file.path) if file else None

    def get_file(self, bucket_name: str, file_path: str, local_path: str):
        self.minio.fget_object(bucket_name, file_path, local_path)

    def put_file(self, bucket_name: str, path: str, local_path: str):
        result = self.minio.fput_object(bucket_name, path, local_path)

    def get_text_file_content(self, bucket_name: str, file_path: str):
        response = None
        try:
            response = self.minio.get_object(bucket_name, file_path)
            return response.data.decode("utf-8")
        finally:
            if response:
                response.close()
                response.release_conn()


class MinioObject:
    def __init__(self, obj: Object):
        self._is_dir = obj.is_dir
        self._path = obj.object_name
        self._last_modified = obj.last_modified
        if self._is_dir:
            self._name = self._path.rsplit("/", 2)[-2]
        else:
            self._name = self._path[self._path.rfind("/") + 1:]

    @property
    def name(self):
        return self._name

    @property
    def path(self):
        return self._path

    @property
    def is_dir(self):
        return self._is_dir

    @property
    def last_modified(self):
        return self._last_modified

    def __repr__(self) -> str:
        return f"[name: {self.name}, path: {self.path}, is_dir: {self.is_dir}, last_modified: {self.last_modified}]"

    def __str__(self) -> str:
        return f"[name: {self.name}, path: {self.path}, is_dir: {self.is_dir}, last_modified: {self.last_modified}]"
