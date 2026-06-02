import logging

from typing import Any
from qubership_pipelines_common_library.v2.secret_manager.model.secret_provider import SecretProvider


class SecretManager:
    """
    Performs CRUD operations on secrets across different secret providers.
    Supports providers: Vault, AWS, GCP, Azure, OpenBao.

    **Initialization example** ::

        secret_manager = SecretManager(
            secret_provider=VaultProvider(
                url="https://our_url",
                credentials=HashicorpVaultCredentialsProvider()
                            .with_env_vars()
                            .get_credentials()
            )
        )

    Then read a secret::

        secret = secret_manager.read_secret(path='path_to_your_secret')

    **Vals-like paths & fragments**

    All path arguments follow a "vals" convention. A path may contain a
    fragment (``#/key/subkey``) to directly retrieve or modify a nested value
    inside a JSON/YAML secret:

    - ``read_secret("myapp/config#/db/host")`` reads only ``config['db']['host']``.
    - ``update_secret("myapp/config#/db/host", "new-host")`` changes that one field without touching the rest.
    - ``delete_secret("myapp/config#/db/host")`` removes the specified key from the secret.

    Without a fragment, the whole secret is returned or operated on as a single unit.

    **Smart MultiStore Provider**

    You can use special `MultiStoreProvider` to resolve secrets without explicitly providing credentials/configuring secret stores.
    It will try to configure requested providers internally using provider type specified in Vals-like secret path, and using system's environment variables.
    Initialization example::

        SecretManager(secret_provider=MultiStoreProvider())

    **Concurrency / thread-safety note**

    Update and delete operations that rely on a read-modify-write cycle
    (fragment updates, fragment deletes, full-secret merges) **assume that
    no other client modifies the same secret concurrently**. The library
    does not lock secrets between the initial read and the final write.
    Simultaneous modifications from multiple instances (or external
    processes) may lead to lost updates or unexpected results.
    """

    def __init__(self, secret_provider: SecretProvider, **kwargs):
        if not secret_provider:
            raise Exception("Initialize SecretManager with one of secret providers first!")
        self.provider = secret_provider

    def read_secret(self, path: str, fail_on_missing: bool = False, default_value = None) -> str | None:
        """
        Read a secret.

        - If the path contains a fragment (``#/key``), only the nested value
          is returned (stringified for non-string types).
        - Without a fragment, the raw secret payload is returned.
        """
        logging.debug(f"Reading secret '{path}' in '{self.provider.get_provider_name()}'...")
        secret = self.provider.read_secret(path=path)
        if secret is None:
            if fail_on_missing:
                raise Exception(f"No secret found for path {path}")
            logging.warning(f"No secret found for path {path} (returning default value)")
            return default_value
        return secret

    def secret_exists(self, path: str) -> bool:
        """Check whether a secret exists at the given path. Implementation might differ in providers, but generally - by attempting to read its value."""
        logging.debug(f"Checking existence of secret '{path}' in '{self.provider.get_provider_name()}'...")
        return self.provider.secret_exists(path)

    def create_secret(self, path: str, data: Any) -> Any:
        """
        Create a new secret.

        - Fragments (``#/key``) are **not** allowed in the path.
        - ``data`` can be a ``dict`` (JSON-serialized) or a plain ``str`` (if provider supports plain strings).
        - Raises an exception if the secret already exists.
        """
        logging.debug(f"Creating secret '{path}' in '{self.provider.get_provider_name()}'...")
        return self.provider.create_secret(path=path, data=data)

    def update_secret(self, path: str, data: Any) -> Any:
        """
        Update an existing secret.

        **With a fragment** (``#/key``):
            - ``data`` must be a scalar value (string, number).
            - Only that nested field is changed; the rest of the secret is untouched.

        **Without a fragment**:
            - If the current secret is a dict and ``data`` is a dict, they are
              **merged** (fields from ``data`` added or overwritten).
            - If both are plain strings, the secret is replaced.
            - Any other combination raises a ``ValueError``.

        The secret must already exist.
        """
        logging.debug(f"Updating secret '{path}' in '{self.provider.get_provider_name()}'...")
        return self.provider.update_secret(path=path, data=data)

    def delete_secret(self, path) -> Any:
        """
        Delete a secret or a part of it.

        - **Without fragment**: permanently deletes the whole secret.
        - **With fragment** (``#/key``): removes only that nested key from a dict secret, leaving the rest intact.
        """
        logging.debug(f"Deleting secret '{path}' in '{self.provider.get_provider_name()}'...")
        return self.provider.delete_secret(path=path)
