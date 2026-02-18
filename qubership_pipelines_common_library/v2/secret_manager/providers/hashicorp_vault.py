import hvac

from typing import Any
from qubership_pipelines_common_library.v2.secret_manager.model.secret_provider import SecretProvider


class HashicorpVaultProvider(SecretProvider):
    DEFAULT_MOUNT_POINT = "secret"

    def __init__(self, url: str = None, mount_point: str = DEFAULT_MOUNT_POINT,
                 token: str = None, verify: bool = True,
                 username: str = None, password: str = None,
                 vault_client: hvac.Client = None, **kwargs):
        """
        Initializes this client to work with **Hashicorp Vault**.
        Requires URL, and one of: token, username/password, or preconfigured hvac.Client
        """
        super().__init__(**kwargs)
        self._mount_point = mount_point
        if vault_client:
            self._vault_client = vault_client
        else:
            if not url:
                raise Exception("Vault URL must be provided")
            if token:
                self._vault_client = hvac.Client(url=url, token=token, verify=verify)
            elif username and password:
                self._vault_client = hvac.Client(url=url, verify=verify)
                self._vault_client.auth.userpass.login(username=username, password=password)
            else:
                raise Exception("Token, username and password, or preconfigured client must be provided")
        if not self._vault_client.is_authenticated():
            raise Exception("Vault Client is not authenticated")

    def read_secret(self, path: str) -> dict[str, Any]:
        response = self._vault_client.secrets.kv.v2.read_secret_version(path=path, mount_point=self._mount_point)
        return response.get("data", {}).get("data")

    def create_or_update_secret(self, path: str, data: dict):
        response = self._vault_client.secrets.kv.v2.create_or_update_secret(
            path=path,
            secret=data,
            mount_point=self._mount_point
        )
        return response

    def delete_secret(self, path: str):
        response = self._vault_client.secrets.kv.v2.delete_metadata_and_all_versions(
            path=path,
            mount_point=self._mount_point
        )
        return response

    def get_provider_name(self) -> str:
        return "hashicorp_vault"
