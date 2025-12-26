import requests

from enum import StrEnum
from qubership_pipelines_common_library.v2.artifacts_finder.model.credentials import Credentials
from qubership_pipelines_common_library.v2.artifacts_finder.model.credentials_provider import CloudCredentialsProvider


class AzureCredentialsProvider(CloudCredentialsProvider):

    tenant_id: str
    client_id: str
    client_secret: str
    target_resource: str
    _auth_data: dict
    _auth_type = None

    class AuthType(StrEnum):
        OAUTH2 = 'OAUTH2'

    def with_oauth2(self,
                    tenant_id: str,
                    client_id: str,
                    client_secret: str,
                    target_resource: str,
                    ):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.target_resource = target_resource
        self.validate_mandatory_attrs(["tenant_id", "client_id", "client_secret", "target_resource"])
        self._auth_data = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": f"{target_resource}/.default"
        }
        self._auth_type = self.AuthType.OAUTH2
        return self

    def with_oauth2_custom_data(self,
                                tenant_id: str,
                                custom_auth_data: dict,
                                ):
        self.tenant_id = tenant_id
        self._auth_data = custom_auth_data
        self.validate_mandatory_attrs(["tenant_id", "_auth_data"])
        self._auth_type = self.AuthType.OAUTH2
        return self

    def get_credentials(self) -> Credentials:
        if self._auth_type is self.AuthType.OAUTH2:
            return self._get_oauth2_credentials()
        else:
            raise ValueError("Need to initialize this provider with AuthType via .with_*auth_type* method first!")

    def _get_oauth2_credentials(self) -> Credentials:
        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        response = requests.post(
            token_url,
            data=self._auth_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        response_json = response.json()
        access_token = response_json.get("access_token")
        if not access_token:
            raise Exception(f"Failed to get access token from {token_url}: {response_json}")

        return Credentials(
            access_token=access_token,
            tenant_id=self.tenant_id,
        )
