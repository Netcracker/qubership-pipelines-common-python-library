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
from webexpythonsdk import WebexAPI


class WebexClient:
    def __init__(self, bot_token: str, proxies: dict = None):
        """ 'proxies' dict for different protocols is passed to requests session.
            e.g. proxies = { 'https' : 'https://user:password@ip:port' }
        """
        self.webex = WebexAPI(
            access_token=bot_token,
            proxies=proxies,
        )
        logging.info("Webex Client configured")

    def send_message(self, room_id: str, msg: str = None, attachment_path: str = None):
        self.webex.messages.create(roomId=room_id, text=msg, files=[attachment_path] if attachment_path else None)
