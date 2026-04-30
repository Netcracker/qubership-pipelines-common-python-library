import json
import os
import yaml
import requests

from typing import Any
from qubership_pipelines_common_library.v1.utils.utils import recursive_merge
from qubership_pipelines_common_library.v1.utils.utils_string import UtilsString
from qubership_pipelines_common_library.v2.artifacts_finder.model.credentials import Credentials
from qubership_pipelines_common_library.v2.secret_manager.model.secret_provider import SecretProvider


class AzureKeyVaultProvider(SecretProvider):
    API_VERSION = "2025-07-01"

    def __init__(self, credentials: Credentials, **kwargs):
        """
        Initializes this client to work with **Azure Key Vault**.
        Requires `Credentials` provided by `AzureCredentialsProvider`.
        Secret paths can only contain alphanumeric characters and dashes
        """
        super().__init__(**kwargs)
        self.PURGE_SECRETS = UtilsString.convert_to_bool(os.getenv('AZURE_KEYVAULT_PURGE_SECRETS', True))
        self.PURGE_TIMEOUT_SECONDS = int(os.getenv('AZURE_KEYVAULT_PURGE_TIMEOUT_SECONDS', 5))
        self._credentials = credentials
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {credentials.access_token}",
            "Content-Type": "application/json",
        })

    def read_secret(self, path: str) -> str | None:
        secret_path, frag = self.parse_vals_path(path)
        vault_url, secret_name, version = self._parse_azure_resource(secret_path)
        payload = self._get_secret_payload(vault_url, secret_name, version)

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

        vault_url, secret_name, version = self._parse_azure_resource(secret_path)
        if version is not None:
            raise ValueError("Version is not allowed when creating a secret")

        if isinstance(data, dict):
            secret_string = json.dumps(data)
        elif isinstance(data, str):
            secret_string = data
        else:
            secret_string = str(data)

        if self._secret_exists(vault_url, secret_name):
            raise Exception(f"Secret at path '{path}' already exists")

        return self._request("PUT", vault_url, self._api_path(secret_name), json_data={"value": secret_string})

    def update_secret(self, path: str, data: Any):
        secret_path, fragment = self.parse_vals_path(path)
        vault_url, secret_name, version = self._parse_azure_resource(secret_path)
        if version is not None:
            raise ValueError("Version is not supported in update_secret")
        payload = self._get_secret_payload(vault_url, secret_name)
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

        return self._request("PUT", vault_url, self._api_path(secret_name), json_data={"value": json.dumps(updated_data)})

    def delete_secret(self, path: str):
        secret_path, fragment = self.parse_vals_path(path)
        vault_url, secret_name, version = self._parse_azure_resource(secret_path)
        if version is not None:
            raise ValueError("Version is not supported in delete_secret")
        if fragment:
            payload = self._get_secret_payload(vault_url, secret_name)
            if payload is None:
                raise Exception(f"Secret to delete not found at path '{path}'")
            current_data = self._payload_to_dict(payload)
            updated_data = self.delete_frag_value(current_data, fragment)
            return self._request("PUT", vault_url, self._api_path(secret_name), json_data={"value": json.dumps(updated_data)})
        else:
            delete_resp = self._request("DELETE", vault_url, self._api_path(secret_name))
            if self.PURGE_SECRETS:
                from time import sleep
                sleep(self.PURGE_TIMEOUT_SECONDS)
                self._request("DELETE", vault_url, f"deletedsecrets/{secret_name}")
            return delete_resp

    def get_provider_name(self) -> str:
        return "azurekeyvault"

    def _request(self, method: str, vault_url: str, api_path: str, json_data: dict = None) -> dict:
        url = f"{vault_url}/{api_path}?api-version={self.API_VERSION}"
        response = self._session.request(method, url, json=json_data)
        response.raise_for_status()
        if response.content:
            return response.json()
        return {}

    def _secret_exists(self, vault_url: str, secret_name: str) -> bool:
        try:
            self._request("GET", vault_url, self._api_path(secret_name))
            return True
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return False
            raise

    def _get_secret_payload(self, vault_url: str, secret_name: str, version: str = None) -> str | None:
        try:
            resp = self._request("GET", vault_url, self._api_path(secret_name, version))
            return resp.get("value", "")
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise

    @staticmethod
    def _parse_azure_resource(secret_path: str) -> tuple[str, str, str]:
        parts = secret_path.split("/", 2)
        vault_host = parts[0]
        if "." in vault_host:
            vault_url = f"https://{vault_host}"
        else:
            vault_url = f"https://{vault_host}.vault.azure.net"
        if len(parts) < 2 or len(parts) > 3:
            raise ValueError("Invalid Azure secret path (should be VAULT-NAME/SECRET-NAME[/VERSION])")
        secret_name = parts[1]
        version = parts[2] if len(parts) == 3 else None
        return vault_url, secret_name, version

    @staticmethod
    def _payload_to_dict(payload: str) -> dict:
        try:
            data = yaml.safe_load(payload)
        except yaml.YAMLError:
            raise ValueError("Secret payload could not be unmarshalled as YAML/JSON")
        if not isinstance(data, dict):
            raise ValueError("Secret payload is not a mapping; cannot apply fragment")
        return data

    @staticmethod
    def _api_path(secret_name: str, version: str = None) -> str:
        if version:
            return f"secrets/{secret_name}/{version}"
        return f"secrets/{secret_name}"
