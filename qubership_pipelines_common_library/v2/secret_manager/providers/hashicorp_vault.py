import json
import os
import hvac

from typing import Any
from hvac.exceptions import Forbidden, InvalidPath
from qubership_pipelines_common_library.v1.utils.utils import recursive_merge
from qubership_pipelines_common_library.v2.artifacts_finder.model.credentials import Credentials
from qubership_pipelines_common_library.v2.secret_manager.model.secret_provider import SecretProvider


class HashicorpVaultProvider(SecretProvider):

    def __init__(self, url: str = None, namespace: str = None, verify: bool = True, credentials: Credentials = None,
                 vault_client: hvac.Client = None, **kwargs):
        """
        Initializes this client to work with **Hashicorp Vault**.
        Requires URL, and Credentials object (from HashicorpVaultCredentialsProvider), or preconfigured hvac.Client
        """
        super().__init__(**kwargs)
        self.mount_versions = {}

        if not vault_client:
            vault_addr = url or os.environ.get("VAULT_ADDR")
            vault_namespace = namespace or os.environ.get("VAULT_NAMESPACE")
            if not vault_addr:
                raise Exception("Vault Address must be provided (via 'url' argument or VAULT_ADDR env variable)")
            if not credentials:
                raise Exception("Credentials object is mandatory")
            if credentials.token:
                self._vault_client = hvac.Client(url=vault_addr, token=credentials.token, verify=verify, namespace=vault_namespace)
            elif credentials.username:
                self._vault_client = hvac.Client(url=vault_addr, username=credentials.username, password=credentials.password, verify=verify, namespace=vault_namespace)
            else:
                raise Exception("Credentials object did not have any valid configurations")
        else:
            self._vault_client = vault_client

        if not self._vault_client.is_authenticated():
            raise Exception("Vault Client is not authenticated")

    def read_secret(self, path: str) -> str | None:
        secret_path_with_mount, frag = self.parse_vals_path(path)
        kv_version, secret_path, mount_point = self._detect_kv_version_and_mount_point(secret_path_with_mount)
        data = self._get_raw_secret_data(secret_path, mount_point, kv_version)

        if frag is None:
            return json.dumps(data) if data is not None else None

        secret_value = self.get_frag_value(data, frag)
        if secret_value is not None and not isinstance(secret_value, str):
            secret_value = str(secret_value)
        return secret_value

    def create_secret(self, path: str, data: Any):
        secret_path_with_mount, frag = self.parse_vals_path(path)
        if frag is not None:
            raise ValueError("Fragment (#/key) in path is not allowed when creating a secret")

        if not isinstance(data, dict):
            raise TypeError(f"{self.get_provider_name()}'s 'create_secret' only accepts a dict; plain string values are not supported")

        kv_version, secret_path, mount_point = self._detect_kv_version_and_mount_point(secret_path_with_mount)

        if self._secret_exists(secret_path, mount_point, kv_version):
            raise Exception(f"Secret at path '{path}' already exists")

        if kv_version == 1:
            self._vault_client.secrets.kv.v1.create_or_update_secret(path=secret_path, secret=data, mount_point=mount_point)
        else:
            self._vault_client.secrets.kv.v2.create_or_update_secret(path=secret_path, secret=data, mount_point=mount_point)

    def update_secret(self, path: str, data: Any):
        secret_path_with_mount, frag = self.parse_vals_path(path)
        kv_version, secret_path, mount_point = self._detect_kv_version_and_mount_point(secret_path_with_mount)

        current_data = self._get_raw_secret_data(secret_path, mount_point, kv_version)
        if current_data is None:
            raise Exception(f"Secret to update not found at path '{path}'")

        if frag is not None:
            if self.is_non_scalar(data):
                raise ValueError("When updating a fragment, data must be a non-dict (string) value")
            updated_data = self.set_frag_value(current_data, frag, data)
        else:
            if isinstance(data, dict):
                updated_data = recursive_merge(current_data, data)
            else:
                raise ValueError("Cannot overwrite a complex secret with a single value")

        if kv_version == 1:
            self._vault_client.secrets.kv.v1.create_or_update_secret(path=secret_path, secret=updated_data, mount_point=mount_point)
        else:
            self._vault_client.secrets.kv.v2.create_or_update_secret(path=secret_path, secret=updated_data, mount_point=mount_point)

    def delete_secret(self, path: str):
        secret_path_with_mount, frag = self.parse_vals_path(path)
        kv_version, secret_path, mount_point = self._detect_kv_version_and_mount_point(secret_path_with_mount)

        if not frag:
            if kv_version == 1:
                self._vault_client.secrets.kv.v1.delete_secret(path=secret_path, mount_point=mount_point)
            else:
                self._vault_client.secrets.kv.v2.delete_metadata_and_all_versions(path=secret_path, mount_point=mount_point)
            return

        current_data = self._get_raw_secret_data(secret_path, mount_point, kv_version)
        if current_data is None:
            raise Exception(f"Secret to delete not found at path '{path}'")
        updated_data = self.delete_frag_value(current_data, frag)

        if kv_version == 1:
            self._vault_client.secrets.kv.v1.create_or_update_secret(path=secret_path, secret=updated_data, mount_point=mount_point)
        else:
            self._vault_client.secrets.kv.v2.create_or_update_secret(path=secret_path, secret=updated_data, mount_point=mount_point)

    def get_provider_name(self) -> str:
        return "vault"

    def secret_exists(self, path: str) -> bool:
        secret_path_with_mount, _ = self.parse_vals_path(path)
        kv_version, secret_path, mount_point = self._detect_kv_version_and_mount_point(secret_path_with_mount)
        return self._secret_exists(secret_path, mount_point, kv_version)

    def _secret_exists(self, secret_path: str, mount_point: str, kv_version: int) -> bool:
        return self._get_raw_secret_data(secret_path, mount_point, kv_version) is not None

    def _get_raw_secret_data(self, secret_path: str, mount_point: str, kv_version: int) -> dict | None:
        try:
            if kv_version == 1:
                response = self._vault_client.secrets.kv.v1.read_secret(path=secret_path, mount_point=mount_point)
                return response.get("data", {})
            else:
                response = self._vault_client.secrets.kv.v2.read_secret_version(path=secret_path, mount_point=mount_point)
                return response.get("data", {}).get("data", {})
        except InvalidPath:
            return None

    def _detect_kv_version_and_mount_point(self, path: str) -> tuple[int, str, str]:
        if path in self.mount_versions:
            return self.mount_versions[path]

        version = 1
        secret_path = path
        mount_point = None
        try:
            response = self._vault_client.read(f"sys/internal/ui/mounts/{path}")
            if response and "data" in response:
                mount_point = response["data"].get("path")
                secret_path = secret_path[len(mount_point):]
                options = response["data"].get("options")
                if options and options.get("version") == "2":
                    version = 2
        except Forbidden as exc:
            raise Exception(f"Permission denied reading mount info for '{path}' - verify permissions OR mount doesn't exist!") from exc
        except Exception as exc:
            raise Exception(f"Unable to detect mount point and version for '{path}'") from exc

        self.mount_versions[path] = (version, secret_path, mount_point)
        return version, secret_path, mount_point
