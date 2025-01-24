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
from pyartifactory import Artifactory
from pyartifactory.exception import PropertyNotFoundError


class ArtifactoryClient:
    def __init__(self, params: dict):
        """
        **`params`** is a dictionary with following mandatory params:

        Arguments:
            url (str): Artifactory host url
            username (str): User used in auth request
            password (str): Token used in auth request
        """
        self.url = params.get("url")
        self.user = params.get("username")
        self.token = params.get("password")
        self.artifactory = Artifactory(url=self.url, auth=(self.user, self.token), api_version=1)
        logging.info("Artifactory Client configured for %s", params.get("url"))

    def get_artifact_properties(self, path_to_artifact: str):
        """"""
        try:
            properties = self.artifactory.artifacts.properties(artifact_path=path_to_artifact)
        except PropertyNotFoundError:
            logging.error("There are not properties for artifact %s", path_to_artifact)
            properties = None
        return properties

    def get_folder_files_list(self, path_to_folder: str):
        """"""
        return self.artifactory.artifacts.list(artifact_path=path_to_folder).files

    def get_artifact_content_by_url(self, path_to_file: str):
        """"""
        file_content = self.artifactory.artifacts.download(artifact_path=path_to_file)
        return file_content.read_text("utf-8")
