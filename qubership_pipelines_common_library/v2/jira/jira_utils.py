import logging
from typing import Any

from qubership_pipelines_common_library.v2.jira.enums.auth_type import AuthType
from jira import JIRA


class JiraUtils:

    @staticmethod
    def create_jira_client(server_url: str, auth_type: AuthType,
                           username: str = None, password: str = None,
                           oauth_dict: dict = None) -> JIRA:
        # PAT in Jira On-Premises - use 'bearer' auth type
        # API Token in Cloud - use 'basic'
        if auth_type == AuthType.BASIC:
            jira_client = JIRA(
                server=server_url,
                basic_auth=(username, password),
                max_retries=3,
                timeout=30
            )
        elif auth_type == AuthType.OAUTH:
            # Note: You'll need to configure OAuth credentials
            # oauth_dict = {
            #     'access_token': password,
            #     'access_token_secret': '',
            #     'consumer_key': username,
            #     'key_cert': None
            # }
            jira_client = JIRA(
                server=server_url,
                oauth=oauth_dict,
                timeout=30
            )
        elif auth_type == AuthType.BEARER:
            jira_client = JIRA(
                server=server_url,
                token_auth=password,
                timeout=30
            )
        else:
            raise Exception('Unknown auth type')

        server_info = jira_client.server_info()
        logging.debug(f"Connected to JIRA {server_info.get('version', 'Unknown')}")
        return jira_client

    @staticmethod
    def serialize_person_ref(person_obj: Any) -> dict | None:
        if person_obj and hasattr(person_obj, 'emailAddress'):
            return {
                "displayName": getattr(person_obj, 'displayName', None),
                "emailAddress": getattr(person_obj, 'emailAddress', None),
                "name": getattr(person_obj, 'name', None),
                "key": getattr(person_obj, 'key', None),
            }
        return None
