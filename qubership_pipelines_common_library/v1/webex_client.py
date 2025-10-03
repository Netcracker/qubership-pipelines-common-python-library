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
        """ **`proxies`** dict for different protocols is passed to requests session.
            e.g. proxies = { 'https' : 'https://user:password@ip:port' }

        Arguments:
            bot_token (str): bot's auth token
            proxies (dict): dict with proxy connections for different protocols
        """
        self.webex = WebexAPI(
            access_token=bot_token,
            proxies=proxies,
        )
        logging.info("Webex Client configured")

    def send_message(self,
                     room_id: str,
                     msg: str = None,
                     attachment_path: str = None,
                     parent_id: str = None,
                     to_person_id: str = None,
                     to_person_email: str = None,
                     markdown: str = None,
                     **request_parameters
                     ):
        """ Post a message to a room.

        Args:
            room_id(str): The room ID.
            to_person_id(str): The ID of the recipient when sending a
                private 1:1 message.
            to_person_email(str): The email address of the recipient when
                sending a private 1:1 message.
            msg(str): The message, in plain text. If `markdown` is
                specified this parameter may be optionally used to provide
                alternate text for UI clients that do not support rich text.
            markdown(str): The message, in Markdown format.
            attachment_path(str): Path to file that will be attached to a message
            parent_id(str): The parent message to reply to. This will
                start or reply to a thread.
            **request_parameters: Additional request parameters (provides
                support for parameters that may be added in the future).
            Returns:
                dict: The API response containing details of the created message.
        """
        response = self.webex.messages.create(roomId=room_id, text=msg, files=[attachment_path] if attachment_path else None,
                                   parentId=parent_id, toPersonId=to_person_id, toPersonEmail=to_person_email,
                                   markdown=markdown, **request_parameters)
        return response
