import boto3

from enum import StrEnum
from botocore.config import Config
from qubership_pipelines_common_library.v2.artifacts_finder.model.credentials import Credentials
from qubership_pipelines_common_library.v2.artifacts_finder.model.credentials_provider import CloudCredentialsProvider


class AwsCredentialsProvider(CloudCredentialsProvider):

    DEFAULT_ROLE_SESSION_NAME = "codeartifact-session"

    access_key: str
    secret_key: str
    session_token: str
    region_name: str
    role_arn: str
    role_session_name: str
    _auth_type = None

    class AuthType(StrEnum):
        DIRECT = 'DIRECT'
        ASSUME_ROLE = 'ASSUME_ROLE'

    def with_direct_credentials(self,
                                access_key: str,
                                secret_key: str,
                                region_name: str,
                                session_token: str | None = None,
                                ):
        self.access_key = access_key
        self.secret_key = secret_key
        self.session_token = session_token
        self.region_name = region_name
        self.validate_mandatory_attrs(["access_key", "secret_key", "region_name"])
        self._auth_type = self.AuthType.DIRECT
        return self

    def with_assume_role(self,
                         access_key: str,
                         secret_key: str,
                         region_name: str,
                         role_arn: str,
                         role_session_name: str | None = DEFAULT_ROLE_SESSION_NAME,
                         ):
        self.access_key = access_key
        self.secret_key = secret_key
        self.region_name = region_name
        self.role_arn = role_arn
        self.role_session_name = role_session_name
        self.validate_mandatory_attrs(["access_key", "secret_key", "region_name", "role_arn", "role_session_name"])
        self._auth_type = self.AuthType.ASSUME_ROLE
        return self

    def get_credentials(self) -> Credentials:
        if self._auth_type is self.AuthType.DIRECT:
            return self._get_direct_credentials()
        elif self._auth_type is self.AuthType.ASSUME_ROLE:
            return self._get_assume_role_credentials()
        else:
            raise ValueError("Need to initialize this provider with AuthType via .with_*auth_type* method first!")

    def get_ecr_authorization_token(self) -> str:
        creds = self.get_credentials()
        ecr_client = boto3.client(
            service_name="ecr",
            config=Config(region_name=self.region_name),
            aws_access_key_id=creds["access_key"],
            aws_secret_access_key=creds["secret_key"],
            aws_session_token=creds["session_token"],
        )
        ecr_authorization_token = ecr_client.get_authorization_token()
        ecr_authorization_data = ecr_authorization_token["authorizationData"][0]
        return ecr_authorization_data["authorizationToken"]

    def _get_direct_credentials(self) -> Credentials:
        return Credentials(
            access_key=self.access_key,
            secret_key=self.secret_key,
            session_token=self.session_token,
            region_name=self.region_name,
        )

    def _get_assume_role_credentials(self) -> Credentials:
        creds = self._assume_role()
        return Credentials(
            access_key=creds["AccessKeyId"],
            secret_key=creds["SecretAccessKey"],
            session_token=creds["SessionToken"],
            role_arn=self.role_arn,
            role_session_name=self.role_session_name,
            region_name=self.region_name,
        )

    def _assume_role(self) -> dict:
        sts_client = boto3.client(
            service_name="sts",
            config=Config(region_name=self.region_name),
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
        )
        assumed = sts_client.assume_role(
            RoleArn=self.role_arn,
            RoleSessionName=self.role_session_name,
        )
        return assumed["Credentials"]
