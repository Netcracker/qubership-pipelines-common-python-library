import json
from enum import StrEnum
from pathlib import Path

from google.auth.transport.requests import AuthorizedSession, Request

from qubership_pipelines_common_library.v2.artifacts_finder.model.credentials import Credentials
from qubership_pipelines_common_library.v2.artifacts_finder.model.credentials_provider import CloudCredentialsProvider


class GcpCredentialsProvider(CloudCredentialsProvider):

    DEFAULT_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]
    DEFAULT_SUBJECT_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:jwt"

    service_account_key_content: str
    oidc_credential_source: dict
    audience: str
    scopes: list[str]
    subject_token_type: str
    _auth_type = None

    class AuthType(StrEnum):
        SA_KEY = 'SA_KEY'
        OIDC_CREDS = 'OIDC_CREDS'

    def with_service_account_key(self,
                                 service_account_key_content: str | None = None,
                                 service_account_key_path: str | Path | None = None,
                                 scopes: list[str] = None,
                                 ):
        if scopes is None:
            scopes = self.DEFAULT_SCOPES
        self.scopes = scopes
        self.service_account_key_content = service_account_key_content
        if service_account_key_path:
            with open(service_account_key_path, 'r') as key_file:
                self.service_account_key_content = key_file.read()
        self.validate_mandatory_attrs(["service_account_key_content"])
        self._auth_type = self.AuthType.SA_KEY
        return self

    def with_oidc_creds(self,
                        oidc_credential_source: dict,
                        audience: str,
                        oidc_token_file_path: str = None,
                        subject_token_type: str = DEFAULT_SUBJECT_TOKEN_TYPE,
                        scopes: list[str] = None,
                        ):
        if scopes is None:
            scopes = self.DEFAULT_SCOPES
        self.scopes = scopes
        self.oidc_credential_source = oidc_credential_source
        if oidc_token_file_path:
            self.oidc_credential_source = {"file": oidc_token_file_path}
        self.audience = audience
        self.subject_token_type = subject_token_type
        self.validate_mandatory_attrs(["oidc_credential_source", "audience"])
        self._auth_type = self.AuthType.OIDC_CREDS
        return self

    def get_credentials(self) -> Credentials:
        if self._auth_type == self.AuthType.SA_KEY:
            from google.oauth2 import service_account
            google_creds = service_account.Credentials.from_service_account_info(
                info=json.loads(self.service_account_key_content),
                scopes=self.scopes,
            )
        elif self._auth_type == self.AuthType.OIDC_CREDS:
            from google.auth import identity_pool
            google_creds = identity_pool.Credentials(
                audience=self.audience,
                subject_token_type=self.subject_token_type,
                credential_source=self.oidc_credential_source,
                scopes=self.scopes,
            )
        else:
            raise ValueError("Need to initialize this provider with AuthType via .with_*auth_type* method first!")

        google_creds.refresh(Request())
        creds = Credentials(
            google_credentials_object=google_creds,
            gcp_authorization_token=google_creds.token, # It can be used in Basic Authorization (in some Execution Commands)
            authorized_session=AuthorizedSession(credentials=google_creds),
        )
        if self._auth_type == self.AuthType.SA_KEY:
            creds.service_account_key_content = self.service_account_key_content
        return creds
