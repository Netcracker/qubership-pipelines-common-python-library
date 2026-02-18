import json
import logging
import requests

from typing import Any
from qubership_pipelines_common_library.v2.artifacts_finder.model.credentials import Credentials
from qubership_pipelines_common_library.v2.secret_manager.model.secret_provider import SecretProvider


class AzureKeyVaultProvider(SecretProvider):
    API_VERSION = "2025-07-01"
    PURGE_SECRETS = False
    PURGE_TIMEOUT_SECONDS = 2

    def __init__(self, credentials: Credentials, vault_name: str, **kwargs):
        """
        Initializes this client to work with **Azure Key Vault**.
        Requires `Credentials` provided by `AzureCredentialsProvider`, and Vault Name.
        Secret paths can only contain alphanumeric characters and dashes
        """
        super().__init__(**kwargs)
        self._credentials = credentials
        self._vault_url = f"https://{vault_name}.vault.azure.net"
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {credentials.access_token}",
            "Content-Type": "application/json",
        })

    def _request(self, method: str, path: str, json_data: dict = None) -> dict:
        url = f"{self._vault_url}/{path}?api-version={self.API_VERSION}"
        response = self._session.request(method, url, json=json_data)
        response.raise_for_status()
        if response.content:
            return response.json()
        return {}

    def read_secret(self, path: str) -> dict[str, Any] | str:
        result = self._request("GET", f"secrets/{path}")
        payload = result.get("value", "")
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            logging.debug("Secret payload is not JSON, returning payload as is")
            return payload

    def create_or_update_secret(self, path: str, data: dict):
        secret_value = json.dumps(data)
        body = {"value": secret_value}
        return self._request("PUT", f"secrets/{path}", json_data=body)

    def delete_secret(self, path: str):
        delete_response = self._request("DELETE", f"secrets/{path}")
        if self.PURGE_SECRETS:
            from time import sleep
            sleep(self.PURGE_TIMEOUT_SECONDS) # W/A, purging immediately leads to 409
            self._request("DELETE", f"deletedsecrets/{path}")
        return delete_response

    def get_provider_name(self) -> str:
        return "azure_key_vault"
