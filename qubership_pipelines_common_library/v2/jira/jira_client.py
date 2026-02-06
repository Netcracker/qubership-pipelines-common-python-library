import os
import json
import logging
import requests

from enum import StrEnum
from typing import Any
from requests import Response
from requests.auth import HTTPBasicAuth
from qubership_pipelines_common_library.v2.utils.retry_decorator import RetryDecorator


class AuthType(StrEnum):
    BASIC = 'basic'
    BEARER = 'bearer'


class JiraClient:

    DEFAULT_FIELD_NAMES_FILTER = [
        "fixVersions",
        "resolution",
        "priority",
        "labels",
        "versions",
        "assignee",
        "status",
        "components",
        "creator",
        "reporter",
        "issuetype",
        "project",
        "resolutiondate",
        "created",
        "updated",
        "description",
        "summary",
        "customfield_10014", # Found in
    ]

    API_VERSION = "2"

    @classmethod
    @RetryDecorator(condition_func=lambda client: client is not None)
    def create_jira_client(cls, host: str, user: str, password: str, auth_type: str,
                           retry_timeout_seconds: int = 180, retry_wait_seconds: int = 1):
        return cls(host, user, password, auth_type)

    def __init__(self, host: str, user: str, password: str, auth_type: str = AuthType.BASIC):
        self.host = host.rstrip("/")
        self.user = user
        self.password = password
        self.session = requests.Session()
        self.session.verify = os.getenv("PYTHONHTTPSVERIFY", "1") != "0"
        if auth_type.lower() == AuthType.BEARER:
            self.session.headers.update({"Authorization": f"Bearer {password}"})
        else:
            self.session.auth = HTTPBasicAuth(user, password)
        self.headers = {"Accept": "application/json", "Content-Type": "application/json"}
        self.session.headers.update(self.headers)
        self.logger = logging.getLogger()
        try:
            self.server_info = self.get_server_info()
            self.deployment_type = self.server_info.get("deploymentType", "Server")
        except Exception as e:
            self.logger.info(f"Could not get Jira instance version, assuming 'Server': {e}")
            self.deployment_type = "Server"
        self.logger.info(f"Jira Client configured for {self.host}, deployment type: {self.deployment_type}")

    @property
    def _is_cloud(self) -> bool:
        return self.deployment_type == "Cloud"

    def get_server_info(self) -> dict[str, Any]:
        retry = 0
        j = self._get_json("serverInfo")
        while not j and retry < 3:
            retry += 1
            j = self._get_json("serverInfo")
        return j

    @RetryDecorator(condition_func=lambda response: response is not None and (response.ok or response.status_code == 400)) # do not retry BadRequest
    def add_ticket_comment(self, ticket_id: str, comment: str, retry_timeout_seconds: int = 180, retry_wait_seconds: int = 1) -> Response:
        response = self.session.post(
            url=f"{self.host}/rest/api/{self.API_VERSION}/issue/{ticket_id}/comment",
            data=json.dumps({"body": comment})
        )
        self.logger.debug(f"Add ticket (id={ticket_id}) comment response: status_code = {response.status_code}, body = {response.text}")
        return response

    def get_latest_ticket_comments(self, ticket_id: str, max_results: int = 50) -> list:
        response = self.session.get(f"{self.host}/rest/api/{self.API_VERSION}/issue/{ticket_id}/comment?maxResults={max_results}&orderBy=-created")
        self.logger.debug(f"Get ticket (id={ticket_id}) comments response: status_code = {response.status_code}, body = {response.text}")
        response.raise_for_status()
        return response.json().get("comments", [])

    @RetryDecorator(condition_func=lambda response: response is not None and (response.ok or response.status_code == 400))
    def create_ticket(self, ticket_fields: dict, retry_timeout_seconds: int = 180, retry_wait_seconds: int = 1) -> Response:
        body = {"fields": ticket_fields}
        response = self.session.post(f"{self.host}/rest/api/{self.API_VERSION}/issue", data=json.dumps(body))
        self.logger.debug(f"Create ticket response: status_code = {response.status_code}, body = {response.text}")
        return response

    def get_createmeta_fields(self, project_key: str, issue_type_name: str) -> dict:
        response = self.session.get(f"{self.host}/rest/api/{self.API_VERSION}/issue/createmeta/{project_key}/issuetypes?maxResults=100")
        self.logger.debug(f"Get createmeta for project (id={project_key}) response: status_code = {response.status_code}, body = {response.text}")
        if not response.ok:
            self.logger.warning(f"Can't get issuetypes by projectKey = {project_key}. Response status = {response.status_code}")
            return {}

        issue_types = response.json().get("issueTypes" if self._is_cloud else "values", [])
        issue_type_ids = [issue_type.get("id") for issue_type in issue_types if issue_type.get("name") == issue_type_name]
        if not issue_type_ids:
            self.logger.warning(f"Can't find issue type id by issue_type_name = {issue_type_name}")
            return {}

        response = self.session.get(f"{self.host}/rest/api/{self.API_VERSION}/issue/createmeta/{project_key}/issuetypes/{issue_type_ids[0]}?maxResults=100")
        self.logger.debug(f"Get createmeta for issuetype (id={issue_type_ids[0]}) response: status_code = {response.status_code}, body = {response.text}")
        if not response.ok:
            self.logger.warning(f"Can't get createmeta by projectKey = {project_key} and issue_type_id = {issue_type_ids[0]}. Response status = {response.status_code}")
            return {}

        fields = response.json().get("fields" if self._is_cloud else "values", [])
        return {field["fieldId"]: field for field in fields}

    def get_ticket_fields(self, ticket_id: str, field_names_filter: list) -> dict:
        response = self.session.get(f"{self.host}/rest/api/{self.API_VERSION}/issue/{ticket_id}?fields={','.join(field_names_filter)}")
        self.logger.debug(f"Get ticket fields (id={ticket_id}) response: status_code = {response.status_code}, body = {response.text}")
        if not response.ok:
            self.logger.warning(f"Can't get ticket info by ticket_id = {ticket_id}. Response status = {response.status_code}")
            return {}
        return self._transform_ticket_fields(response.json().get("fields", {}))

    def get_editmeta_fields(self, ticket_id: str) -> dict:
        response = self.session.get(f"{self.host}/rest/api/{self.API_VERSION}/issue/{ticket_id}/editmeta")
        self.logger.debug(f"Get editmeta for ticket (id={ticket_id}) response: status_code = {response.status_code}, body = {response.text}")
        if not response.ok:
            self.logger.warning(f"Can't get ticket {ticket_id} editmeta. Response status = {response.status_code}")
            return {}
        return response.json().get("fields", {})

    @RetryDecorator(condition_func=lambda response: response is not None and (response.ok or response.status_code == 400))
    def update_ticket(self, ticket_id: str, ticket_fields: dict,
                      retry_timeout_seconds: int = 180, retry_wait_seconds: int = 1) -> Response:
        body = {"fields": ticket_fields}
        response = self.session.put(f"{self.host}/rest/api/{self.API_VERSION}/issue/{ticket_id}", data=json.dumps(body))
        self.logger.debug(f"Update ticket (id={ticket_id}) response: status_code = {response.status_code}, body = {response.text}")
        return response

    def get_ticket_transitions(self, ticket_id: str):
        response = self.session.get(f"{self.host}/rest/api/{self.API_VERSION}/issue/{ticket_id}/transitions?expand=transitions.fields")
        self.logger.debug(f"Get ticket (id={ticket_id}) transitions response: status_code = {response.status_code}, body = {response.text}")
        if not response.ok:
            self.logger.warning(f"Ticket {ticket_id} transitions are not found in response. Response status = {response.status_code}")
            return []
        return response.json().get("transitions", [])

    def find_applicable_transition(self, transitions: list, status_name: str, transition_name: str = ""):
        transitions_by_next_status = [transition for transition in transitions if status_name.lower() == transition.get("to", {}).get("name", "").lower()]
        if not transitions_by_next_status:
            self.logger.error(f"Status '{status_name}' is not found in transitions.")
            return None

        if len(transitions_by_next_status) > 1:
            self.logger.warning(f"Found more than one transition to status '{status_name}'")
            if transition_name:
                transitions_by_name = [transition for transition in transitions_by_next_status if transition_name.lower() == transition.get("name", "").lower()]
                if transitions_by_name:
                    return transitions_by_name[0]
                else:
                    self.logger.warning(f"Transition '{transition_name}' is not found in transitions. Will use first found transition by status '{status_name}'.")

        return transitions_by_next_status[0]

    def perform_ticket_transition(self, ticket_id: str, transition_id: str, transition_fields):
        body = {"transition": {"id": transition_id}}
        if transition_fields:
            body["fields"] = transition_fields
        response = self.session.post(f"{self.host}/rest/api/{self.API_VERSION}/issue/{ticket_id}/transitions", data=json.dumps(body))
        self.logger.debug(f"Perform transition for ticket (id={ticket_id}) response: status_code = {response.status_code}, body = {response.text}")
        return response

    def _get_json(self, path: str, params: dict[str, Any] | None = None, use_post: bool = False) -> dict | list:
        url = f"{self.host}/rest/api/{self.API_VERSION}/{path}"
        response = (
            self.session.post(url, data=json.dumps(params))
            if use_post
            else self.session.get(url, params=params)
        )
        return response.json()

    @staticmethod
    def filter_ticket_fields(ticket_fields: dict, meta_fields_filter: dict) -> dict:
        return {field_key: field_value for field_key, field_value in ticket_fields.items() if field_key in meta_fields_filter.keys()}

    @staticmethod
    def _transform_ticket_fields(ticket_fields_json: dict):
        filtered_fields = {}
        for k, v in ticket_fields_json.items():
            if isinstance(v, dict) and "emailAddress" in v:
                filtered_fields[k] = JiraClient.serialize_person_ref(v)
            else:
                filtered_fields[k] = v
        return filtered_fields

    @staticmethod
    def serialize_person_ref(person: dict) -> dict | None:
        if person:
            return {
                "displayName": person.get("displayName", None),
                "emailAddress": person.get("emailAddress", None),
                "name": person.get("name", None),
                "key": person.get("key", None),
            }
        return None
