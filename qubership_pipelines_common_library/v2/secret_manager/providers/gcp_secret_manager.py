import json
import os
import yaml

from typing import Any
from qubership_pipelines_common_library.v1.utils.utils import recursive_merge
from qubership_pipelines_common_library.v2.artifacts_finder.model.credentials import Credentials
from qubership_pipelines_common_library.v2.secret_manager.model.secret_provider import SecretProvider
from google.cloud import secretmanager
from google.api_core import exceptions


class GcpSecretManagerProvider(SecretProvider):

    def __init__(self, credentials: Credentials, **kwargs):
        """
        Initializes this client to work with **GCP Secret Manager**.
        Requires `Credentials` provided by `GcpCredentialsProvider`.
        GCP secret paths (or IDs) can't include slashes, only hyphens and underscores, and are limited to 255 characters.
        """
        super().__init__(**kwargs)
        self._credentials = credentials
        self._gcp_client = secretmanager.SecretManagerServiceClient(
            credentials=self._credentials.google_credentials_object
        )

    def read_secret(self, path: str) -> str | None:
        secret_path, frag = self.parse_vals_path(path)
        payload = self._get_secret_payload(secret_path)

        if payload is None:
            return None
        if not frag:
            return payload

        data = self._payload_to_dict(payload)
        secret_value = self.get_frag_value(data, frag)
        if secret_value is not None and not isinstance(secret_value, str):
            secret_value = str(secret_value)
        return secret_value

    def create_secret(self, path: str, data: Any):
        secret_path, frag = self.parse_vals_path(path)
        if frag is not None:
            raise ValueError("Fragment (#/key) in path is not allowed when creating a secret")

        if isinstance(data, dict):
            secret_string = json.dumps(data)
        elif isinstance(data, str):
            secret_string = data
        else:
            secret_string = str(data)

        if self._secret_exists(secret_path):
            raise Exception(f"Secret at path '{path}' already exists")

        project, secret_id = self._get_project_and_secret_id(secret_path)
        parent = f"projects/{project}"
        self._gcp_client.create_secret(
            parent=parent,
            secret_id=secret_id,
            secret={"replication": {"automatic": {}}},
        )
        return self._gcp_client.add_secret_version(
            request={
                "parent": f"{parent}/secrets/{secret_id}",
                "payload": {"data": secret_string.encode("utf-8")},
            }
        )

    def update_secret(self, path: str, data: Any):
        secret_path, fragment = self.parse_vals_path(path)
        payload = self._get_secret_payload(secret_path)
        if payload is None:
            raise Exception(f"Secret to update not found at path '{path}'")
        try:
            current_data = yaml.safe_load(payload)
        except yaml.YAMLError:
            current_data = payload

        if fragment is not None:
            if not isinstance(current_data, dict):
                raise ValueError("Secret payload is not a mapping; cannot apply fragment")
            if self.is_non_scalar(data):
                raise ValueError("When updating a fragment, data must be a non-dict (string) value")
            updated_data = self.set_frag_value(current_data, fragment, data)
        else:
            if isinstance(data, dict) and isinstance(current_data, dict):
                updated_data = recursive_merge(current_data, data)
            elif isinstance(data, str) and isinstance(current_data, str):
                updated_data = data
            else:
                raise ValueError("Cannot overwrite a complex secret with a single value")

        project, secret_id = self._get_project_and_secret_id(secret_path)
        return self._gcp_client.add_secret_version(
            request={
                "parent": f"projects/{project}/secrets/{secret_id}",
                "payload": {"data": json.dumps(updated_data).encode("utf-8")},
            }
        )

    def delete_secret(self, path: str):
        secret_path, fragment = self.parse_vals_path(path)
        project, secret_id = self._get_project_and_secret_id(secret_path)
        if fragment:
            payload = self._get_secret_payload(secret_path)
            if payload is None:
                raise Exception(f"Secret to delete not found at path '{path}'")
            current_data = self._payload_to_dict(payload)
            updated_data = self.delete_frag_value(current_data, fragment)
            new_payload = json.dumps(updated_data)
            return self._gcp_client.add_secret_version(
                request={
                    "parent": f"projects/{project}/secrets/{secret_id}",
                    "payload": {"data": new_payload.encode("utf-8")},
                }
            )
        else:
            return self._gcp_client.delete_secret(request={"name": f"projects/{project}/secrets/{secret_id}"})

    def get_provider_name(self) -> str:
        return "gcpsecrets"

    def _secret_exists(self, secret_path: str) -> bool:
        project, secret_id = self._get_project_and_secret_id(secret_path)
        name = f"projects/{project}/secrets/{secret_id}"
        try:
            self._gcp_client.get_secret(request={"name": name})
            return True
        except exceptions.NotFound:
            return False

    def _get_secret_payload(self, secret_path: str) -> str | None:
        project, secret_id = self._get_project_and_secret_id(secret_path)
        resource = f"projects/{project}/secrets/{secret_id}/versions/latest"
        try:
            response = self._gcp_client.access_secret_version(request={"name": resource})
            return response.payload.data.decode("utf-8")
        except exceptions.NotFound:
            return None

    @staticmethod
    def _get_project_and_secret_id(secret_path: str) -> tuple[str, str]:
        if "/" in secret_path:
            return secret_path.split("/", 1)
        project = os.getenv("GCP_PROJECT")
        if not project:
            raise ValueError("No project found in secret path and GCP_PROJECT environment variable is not set")
        return project, secret_path

    @staticmethod
    def _payload_to_dict(payload: str) -> dict:
        try:
            current_data = yaml.safe_load(payload)
        except yaml.YAMLError:
            raise ValueError("Secret payload could not be unmarshalled as YAML/JSON")
        if not isinstance(current_data, dict):
            raise ValueError("Secret payload is not a mapping; cannot apply fragment")
        return current_data
