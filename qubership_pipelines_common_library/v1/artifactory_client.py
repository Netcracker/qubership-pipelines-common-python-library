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
from dataclasses import dataclass

import requests
from requests.auth import HTTPBasicAuth


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
        self.artifactory = ArtifactoryAPI(self.url, HTTPBasicAuth(self.user, self.token))
        logging.info("Artifactory Client configured for %s", params.get("url"))

    def get_artifact_properties(self, path_to_artifact: str):
        """"""
        try:
            properties = self.artifactory.get_artifact_properties(artifact_path=path_to_artifact)
        except ArtifactoryError:
            logging.error("There are not properties for artifact %s", path_to_artifact)
            properties = None
        return properties

    def get_folder_files_list(self, path_to_folder: str):
        """"""
        return self.artifactory.get_files_list(artifact_path=path_to_folder)

    def get_artifact_content_by_url(self, path_to_file: str):
        """"""
        return self.artifactory.get_file_content(artifact_path=path_to_file)


class ArtifactoryAPI:
    def __init__(self, api_url: str, auth, verify=False):
        self.api_url = api_url.rstrip('/')
        self._session = requests.session()
        self._session.verify = False
        if auth:
            self._session.auth = auth

    def _get(self, url):
        response = self._session.get(url)
        response.raise_for_status()
        return response

    def get_artifact_info(self, artifact_path: str):
        try:
            response = self._get(f"{self.api_url}/api/storage/{artifact_path}").json()
            artifact_info = ArtifactInfo(repo=response['repo'], path=response['path'])
            return artifact_info
        except requests.exceptions.HTTPError as error:
            raise ArtifactoryError from error

    def get_artifact_properties(self, artifact_path: str):
        try:
            response = self._get(f"{self.api_url}/api/storage/{artifact_path}?properties").json()
            return ArtifactProperties(properties=response['properties'])
        except requests.exceptions.HTTPError as error:
            raise ArtifactoryError from error

    def get_files_list(self, artifact_path: str):
        try:
            response = self._get(f"{self.api_url}/api/storage/{artifact_path}?list&deep=1&listFolders=1").json()
            return [ArtifactListEntry(uri=f['uri'], size=int(f['size']), folder=(f['folder'] is True)) for f in
                    response['files']]
        except requests.exceptions.HTTPError as error:
            raise ArtifactoryError from error

    def get_file_content(self, artifact_path: str):
        try:
            info = self.get_artifact_info(artifact_path)
            return self._get(f"{self.api_url}/{info.repo}{info.path}").content.decode("utf-8")
        except requests.exceptions.HTTPError as error:
            raise ArtifactoryError from error


class ArtifactoryError(Exception):
    pass


@dataclass
class ArtifactInfo:
    repo: str
    path: str


@dataclass
class ArtifactProperties:
    properties: dict


@dataclass
class ArtifactListEntry:
    uri: str
    size: int
    folder: bool
