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


class ArtifactoryClient:
    def __init__(self, params: dict):
        self.url = params.get("url")
        self.user = params.get("username")
        self.token = params.get("password")
        self.artifactory = Artifactory(url=self.url, auth=(self.user, self.token), api_version=1)
        logging.info("Artifactory Client configured for %s %s %s", params.get("url"),
                     params.get("username"), params.get("password"))

