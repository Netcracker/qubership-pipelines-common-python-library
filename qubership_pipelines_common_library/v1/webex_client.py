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
import mimetypes
import os
import time
import json as jsonlib
from urllib import parse
from collections import namedtuple, OrderedDict
from requests_toolbelt import MultipartEncoder

EncodableFile = namedtuple(
    "EncodableFile", ["file_name", "file_object", "content_type"]
)


class WebexClient:
    DEFAULT_BASE_URL = "https://webexapis.com/v1/"

    def __init__(self, bot_token: str, proxies: dict = None):
        """ **`proxies`** dict for different protocols is passed to requests session.
            e.g. proxies = { 'https' : 'https://user:password@ip:port' }
            Backport for 3.9 doesn't use official Webex SDK lib and only supports sending messages

        Arguments:
            bot_token (str): bot's auth token
            proxies (dict): dict with proxy connections for different protocols
        """
        self._session = RestSession(
            access_token=bot_token,
            base_url=WebexClient.DEFAULT_BASE_URL,
            proxies=proxies,
        )
        self.messages = MessagesAPI(self._session)
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
        """
        self.messages.create(roomId=room_id, text=msg, files=[attachment_path] if attachment_path else None,
                             parentId=parent_id, toPersonId=to_person_id, toPersonEmail=to_person_email,
                             markdown=markdown, **request_parameters)


class RestSession(object):
    DEFAULT_SINGLE_REQUEST_TIMEOUT = 60
    DEFAULT_WAIT_ON_RATE_LIMIT = True
    RATE_LIMIT_RESPONSE_CODE = 429

    def __init__(
        self,
        access_token,
        base_url,
        single_request_timeout=DEFAULT_SINGLE_REQUEST_TIMEOUT,
        wait_on_rate_limit=DEFAULT_WAIT_ON_RATE_LIMIT,
        proxies=None,
        disable_ssl_verify=False,
    ):
        self._base_url = base_url
        self._access_token = str(access_token)
        self._single_request_timeout = single_request_timeout
        self._wait_on_rate_limit = wait_on_rate_limit

        self._req_session = requests.session()

        if disable_ssl_verify:
            self._req_session.verify = False

        if proxies is not None:
            self._req_session.proxies.update(proxies)

        self._req_session.headers.update({
            "Authorization": "Bearer " + access_token,
            "Content-type": "application/json;charset=utf-8",
            "User-Agent": "qubership-common-library/0.1.3",
        })

    def request(self, method, url, erc, **kwargs):
        abs_url = self.abs_url(url)
        kwargs.setdefault("timeout", self._single_request_timeout)
        while True:
            response = self._req_session.request(method, abs_url, **kwargs)
            if response.status_code == RestSession.RATE_LIMIT_RESPONSE_CODE:
                retry_after = max(1, int(response.headers.get("Retry-After", 15)))
                time.sleep(retry_after)
                continue
            elif response.status_code == erc:
                return response
            else:
                raise Exception(f"Unexpected status_code: {response.status_code}")

    def abs_url(self, url):
        parsed_url = parse.urlparse(url)
        if not parsed_url.scheme and not parsed_url.netloc:
            return parse.urljoin(str(self._base_url), str(url))
        else:
            return url

    def post(self, url, json=None, data=None, **kwargs):
        response = self.request(
            "POST", url, 200, json=json, data=data, **kwargs
        )
        return jsonlib.loads(response.text, object_hook=OrderedDict)


class MessagesAPI(object):
    API_ENDPOINT = "messages"

    def __init__(self, session: RestSession):
        self._session = session

    def create(
        self,
        roomId: str = None,
        parentId: str = None,
        toPersonId: str = None,
        toPersonEmail: str = None,
        text: str = None,
        markdown: str = None,
        files: list[str] = None,
        **request_parameters,
    ):
        if files:
            if len(files) > 1:
                raise ValueError(
                    "The `files` parameter should be a list with "
                    "exactly one (1) item. The files parameter "
                    "is a list, which accepts multiple values to "
                    "allow for future expansion, but currently "
                    "only one file may be included with the "
                    "message."
                )
        else:
            files = None

        post_data = self._dict_from_items_with_values(
            request_parameters,
            roomId=roomId,
            toPersonId=toPersonId,
            toPersonEmail=toPersonEmail,
            text=text,
            markdown=markdown,
            files=files,
            parentId=parentId,
        )

        if not files or self._is_web_url(files[0]):
            json_data = self._session.post(MessagesAPI.API_ENDPOINT, json=post_data)
        else:
            try:
                post_data["files"] = self._open_local_file(files[0])
                multipart_data = MultipartEncoder(post_data)
                headers = {"Content-type": multipart_data.content_type}
                json_data = self._session.post(
                    MessagesAPI.API_ENDPOINT, headers=headers, data=multipart_data
                )
            finally:
                post_data["files"].file_object.close()

        return json_data


    def _dict_from_items_with_values(self, *dictionaries, **items):
        dict_list = list(dictionaries)
        dict_list.append(items)
        result = {}
        for d in dict_list:
            for key, value in d.items():
                if value is not None:
                    result[key] = value
        return result

    def _is_web_url(self, string):
        parsed_url = parse.urlparse(string)
        return (
                parsed_url.scheme.lower() == "http"
                or parsed_url.scheme.lower() == "https"
        ) and parsed_url.netloc

    def _open_local_file(self, file_path):
        file_name = os.path.basename(file_path)
        file_object = open(file_path, "rb")
        content_type = mimetypes.guess_type(file_name)[0] or "text/plain"
        return EncodableFile(
            file_name=file_name, file_object=file_object, content_type=content_type
        )
