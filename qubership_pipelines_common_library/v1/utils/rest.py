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
import requests
from requests.auth import HTTPBasicAuth

from http_exceptions import UnauthorizedException, NotFoundException, ClientException, ServerException

from v1.log_client import LogClient

class RestClient:
    def __init__(self, host: str, user: str, password: str):
        self.host = host.rstrip('/')
        session = requests.Session()
        session.verify = False
        session.auth = HTTPBasicAuth(user, password)
        self.session = session
        self.logger = LogClient()

    def get(self, path: str, headers=None):
        logging.info("GET request started for url: %s", self.host + path)
        if headers is None:
            headers = dict()

        response = self.session.get(url=self.host + path, headers=headers, verify=False)

        if response.status_code != 200:
            logging.error("Error response " + str(response.status_code))

        if response.status_code == 401:
            raise UnauthorizedException(response.text)
        elif response.status_code == 404:
            raise NotFoundException(response.text)
        elif 400 <= response.status_code <= 500:
            raise ClientException(response.status_code)
        elif response.status_code >= 500:
            raise ServerException(response.status_code)
        return response

    def post(self, path: str, body=None, headers=None):
        if headers is None:
            headers = dict()

        response = self.session.post(url=self.host + path, data=body, headers=headers, verify=False)

        if response.status_code != 200:
            logging.error("Error response " + str(response.status_code))

        if response.status_code == 401:
            raise UnauthorizedException(response.text)
        elif response.status_code == 404:
            raise NotFoundException(response.text)
        elif 400 <= response.status_code <= 500:
            raise ClientException(response.status_code)
        elif response.status_code >= 500:
            raise ServerException(response.status_code)
        return response