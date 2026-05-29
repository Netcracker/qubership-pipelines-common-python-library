import os
import hvac

from qubership_pipelines_common_library.v2.artifacts_finder.model.credentials import Credentials
from qubership_pipelines_common_library.v2.secret_manager.providers.hashicorp_vault import HashicorpVaultProvider


class OpenBaoProvider(HashicorpVaultProvider):

    # noinspection PyMissingConstructor
    def __init__(self, url: str = None, namespace: str = None, verify: bool = True, credentials: Credentials = None,
                 vault_client: hvac.Client = None, **kwargs):
        """
        Initializes this client to work with **OpenBao**.
        Requires URL, and Credentials object (from OpenBaoCredentialsProvider), or preconfigured hvac.Client
        Currently is API-compatible with Vault
        """
        self.mount_versions = {}

        if not vault_client:
            openbao_addr = url or os.environ.get("BAO_ADDR")
            openbao_namespace = namespace or os.environ.get("BAO_NAMESPACE")
            if not openbao_addr:
                raise Exception("Vault Address must be provided (via 'url' argument or BAO_ADDR env variable)")
            if not credentials:
                raise Exception("Credentials object is mandatory")
            if credentials.token:
                self._vault_client = hvac.Client(url=openbao_addr, token=credentials.token, verify=verify, namespace=openbao_namespace)
            elif credentials.username:
                self._vault_client = hvac.Client(url=openbao_addr, username=credentials.username, password=credentials.password, verify=verify, namespace=openbao_namespace)
            else:
                raise Exception("Credentials object did not have any valid configurations")
        else:
            self._vault_client = vault_client

        if not self._vault_client.is_authenticated():
            raise Exception("OpenBao Client is not authenticated")

    def get_provider_name(self) -> str:
        return "openbao"
