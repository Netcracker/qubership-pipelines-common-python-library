import os
from typing import Any
from urllib.parse import urlparse, unquote

from qubership_pipelines_common_library.v2.artifacts_finder.auth.aws_credentials import AwsCredentialsProvider
from qubership_pipelines_common_library.v2.artifacts_finder.auth.azure_credentials import AzureCredentialsProvider
from qubership_pipelines_common_library.v2.artifacts_finder.auth.gcp_credentials import GcpCredentialsProvider
from qubership_pipelines_common_library.v2.artifacts_finder.auth.hashicorp_vault_credentials import HashicorpVaultCredentialsProvider
from qubership_pipelines_common_library.v2.artifacts_finder.auth.openbao_credentials import OpenBaoCredentialsProvider
from qubership_pipelines_common_library.v2.secret_manager.model.secret_provider import SecretProvider
from qubership_pipelines_common_library.v2.secret_manager.providers.aws_secrets_manager import AwsSecretsManagerProvider
from qubership_pipelines_common_library.v2.secret_manager.providers.azure_key_vault import AzureKeyVaultProvider
from qubership_pipelines_common_library.v2.secret_manager.providers.gcp_secret_manager import GcpSecretManagerProvider
from qubership_pipelines_common_library.v2.secret_manager.providers.hashicorp_vault import HashicorpVaultProvider
from qubership_pipelines_common_library.v2.secret_manager.providers.openbao import OpenBaoProvider


class MultiStoreProvider(SecretProvider):

    STORE_ID_PARAM_NAME = "secret_store_id"

    PROVIDER_MAP = {
        "awssecrets": AwsSecretsManagerProvider,
        "azurekeyvault": AzureKeyVaultProvider,
        "gcpsecrets": GcpSecretManagerProvider,
        "openbao": OpenBaoProvider,
        "vault": HashicorpVaultProvider,
    }

    CREDENTIALS_MAP = {
        "awssecrets": AwsCredentialsProvider,
        "azurekeyvault": AzureCredentialsProvider,
        "gcpsecrets": GcpCredentialsProvider,
        "openbao": OpenBaoCredentialsProvider,
        "vault": HashicorpVaultCredentialsProvider,
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._cache = {}

    def read_secret(self, path: str) -> str | None:
        provider_type, store_id = self._parse_uri(path)
        cache_key = (provider_type, store_id or "default")
        if cache_key not in self._cache:
            self._cache[cache_key] = self._build_provider(provider_type, store_id)
        return self._cache[cache_key].read_secret(path)

    def create_secret(self, path: str, data: Any):
        raise NotImplementedError("MultiStoreProvider can only read secrets!")

    def update_secret(self, path: str, data: Any):
        raise NotImplementedError("MultiStoreProvider can only read secrets!")

    def delete_secret(self, path: str):
        raise NotImplementedError("MultiStoreProvider can only read secrets!")

    def get_provider_name(self) -> str:
        return "multistore"

    def _parse_uri(self, path: str) -> tuple[str, str | None]:
        parsed = urlparse(path)
        if "+" not in parsed.scheme:
            raise ValueError(f"Invalid VALS URI scheme: '{parsed.scheme}' in '{path}'")
        provider_type = parsed.scheme.split("+", 1)[1]
        if provider_type not in self.PROVIDER_MAP:
            raise ValueError(f"Unknown provider type '{provider_type}' in '{path}'")
        query_params = {}
        if parsed.query:
            query_params = dict(p.split("=", 1) for p in parsed.query.split("&"))
        store_id = query_params.get(self.STORE_ID_PARAM_NAME)
        if store_id is not None:
            store_id = unquote(store_id)
        return provider_type, store_id

    def _build_provider(self, provider_type: str, store_id: str | None) -> SecretProvider:
        prefix = f"{store_id}_" if store_id else ""
        creds_provider = self.CREDENTIALS_MAP[provider_type]
        creds = creds_provider().with_env_vars(prefix=prefix).get_credentials()
        provider_cls = self.PROVIDER_MAP[provider_type]

        if provider_type == "vault":
            url = os.getenv(f"{prefix}VAULT_ADDR")
            namespace = os.getenv(f"{prefix}VAULT_NAMESPACE")
            if not url:
                raise ValueError(f"Vault address not found: set {prefix}VAULT_ADDR")
            return provider_cls(url=url, namespace=namespace, credentials=creds)

        if provider_type == "openbao":
            url = os.getenv(f"{prefix}BAO_ADDR")
            namespace = os.getenv(f"{prefix}BAO_NAMESPACE")
            if not url:
                raise ValueError(f"OpenBao address not found: set {prefix}BAO_ADDR")
            return provider_cls(url=url, namespace=namespace, credentials=creds)

        return provider_cls(credentials=creds)
