import logging

from typing import Any
from qubership_pipelines_common_library.v2.secret_manager.model.secret_provider import SecretProvider


class SecretManager:
    """
    Performs CRUD operations on secrets in different secret providers.

    Supports different secret providers: Vault, AWS, GCP, Azure.

    Start by initializing this client with one of implementations:
    ``secret_manager = SecretManager(secret_provider=VaultProvider(url="https://our_url", username="user", password="password"))``

    Then read your secret using
    ``secret = secret_manager.read_secret(path='path_to_your_secret')``

    For more complex providers (e.g. GCP Secret Manager), you need to use specific Credential Providers
    As an example:
    ```
    gcp_creds = GcpCredentialsProvider().with_service_account_key(...all the required params...).get_credentials()
    gcp_secret_provider = GcpSecretManagerProvider(creds=gcp_creds, project='our_project')
    secret_manager = SecretManager(secret_provider=gcp_secret_provider)
    ```
    """

    def __init__(self, secret_provider: SecretProvider, **kwargs):
        if not secret_provider:
            raise Exception("Initialize SecretManager with one of secret providers first!")
        self.provider = secret_provider

    def read_secret(self, path: str) -> dict[str, Any] | str:
        logging.debug(f"Reading secret by path '{path}' in '{self.provider.get_provider_name()}'...")
        return self.provider.read_secret(path=path)

    def create_or_update_secret(self, path, data) -> Any:
        logging.debug(f"Creating/Updating secret by path '{path}' in '{self.provider.get_provider_name()}'...")
        return self.provider.create_or_update_secret(path=path, data=data)

    def delete_secret(self, path) -> Any:
        logging.debug(f"Deleting secret by path '{path}' in '{self.provider.get_provider_name()}'...")
        return self.provider.delete_secret(path=path)
