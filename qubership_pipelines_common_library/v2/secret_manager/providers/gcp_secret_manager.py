import json
import logging

from typing import Any
from qubership_pipelines_common_library.v2.artifacts_finder.model.credentials import Credentials
from qubership_pipelines_common_library.v2.secret_manager.model.secret_provider import SecretProvider
from google.cloud import secretmanager
from google.api_core import exceptions


class GcpSecretManagerProvider(SecretProvider):

    def __init__(self, credentials: Credentials, project: str, **kwargs):
        """
        Initializes this client to work with **GCP Secret Manager**.
        Requires `Credentials` provided by `GcpCredentialsProvider`.
        GCP secret paths (or IDs) can't include slashes, only hyphens and underscores, and are limited to 255 characters.
        """
        super().__init__(**kwargs)
        self._credentials = credentials
        self._project = project
        self._gcp_client = secretmanager.SecretManagerServiceClient(
            credentials=self._credentials.google_credentials_object
        )

    def read_secret(self, path: str) -> dict[str, Any] | str:
        name = f"projects/{self._project}/secrets/{path}/versions/latest"
        response = self._gcp_client.access_secret_version(request={"name": name})
        payload = response.payload.data.decode("utf-8")
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            logging.debug("Secret payload is not JSON, returning payload as is")
            return payload

    def create_or_update_secret(self, path: str, data: dict):
        secret_name = f"projects/{self._project}/secrets/{path}"

        try:
            self._gcp_client.get_secret(request={"name": secret_name})
        except exceptions.NotFound:
            logging.debug(f"Creating new secret '{secret_name}'...")
            self._gcp_client.create_secret(
                parent=f"projects/{self._project}",
                secret_id=path,
                secret={"replication": {"automatic": {}}},
            )

        logging.debug(f"Adding secret version to '{secret_name}'...")
        payload_bytes = json.dumps(data).encode("utf-8")
        response = self._gcp_client.add_secret_version(
            request={
                "parent": secret_name,
                "payload": {"data": payload_bytes},
            }
        )
        return response

    def delete_secret(self, path: str) -> dict[str, Any]:
        secret_name = f"projects/{self._project}/secrets/{path}"
        return self._gcp_client.delete_secret(request={"name": secret_name})

    def get_provider_name(self) -> str:
        return "gcp_secret_manager"
