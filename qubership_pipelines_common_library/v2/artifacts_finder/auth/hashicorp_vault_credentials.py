import os
from enum import StrEnum
from qubership_pipelines_common_library.v2.artifacts_finder.model.credentials import Credentials
from qubership_pipelines_common_library.v2.artifacts_finder.model.credentials_provider import CloudCredentialsProvider
from qubership_pipelines_common_library.v2.utils.env_var_utils import EnvVarUtils


class HashicorpVaultCredentialsProvider(CloudCredentialsProvider):

    token: str = None
    username: str = None
    password: str = None
    _auth_type = None

    class AuthType(StrEnum):
        TOKEN = 'TOKEN'
        USERPASS = 'USERPASS'

    def with_token(self, token: str):
        self.token = token
        self.validate_mandatory_attrs(["token"])
        self._auth_type = self.AuthType.TOKEN
        return self

    def with_userpass(self, username: str, password: str):
        self.username = username
        self.password = password
        self.validate_mandatory_attrs(["username", "password"])
        self._auth_type = self.AuthType.USERPASS
        return self

    def with_env_vars(self):
        if token := os.getenv("VAULT_TOKEN"):
            self.token = token
            self._auth_type = self.AuthType.TOKEN
        elif username := os.getenv("VAULT_USERNAME"):
            self.username = username
            self.password = EnvVarUtils.get_from_env_or_file("VAULT_PASSWORD")
            self._auth_type = self.AuthType.USERPASS
        else:
            raise ValueError("Could not find required environment variables (VAULT_TOKEN or VAULT_USERNAME)")
        return self

    def get_credentials(self) -> Credentials:
        if self._auth_type is None:
            raise ValueError("Need to initialize this provider with AuthType via .with_*auth_type* method first!")
        return Credentials(
            token=self.token,
            username=self.username,
            password=self.password,
        )
