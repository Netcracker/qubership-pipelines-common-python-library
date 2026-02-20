import json
import logging
import boto3

from typing import Any
from botocore.config import Config
from botocore.exceptions import ClientError
from qubership_pipelines_common_library.v2.artifacts_finder.model.credentials import Credentials
from qubership_pipelines_common_library.v2.secret_manager.model.secret_provider import SecretProvider


class AwsSecretsManagerProvider(SecretProvider):

    def __init__(self, credentials: Credentials, **kwargs):
        """
        Initializes this client to work with **AWS Secrets Manager**.
        Requires `Credentials` provided by `AwsCredentialsProvider`.
        """
        super().__init__(**kwargs)
        self._credentials = credentials
        self._aws_client = boto3.client(
            service_name='secretsmanager',
            config=Config(region_name=credentials.region_name),
            aws_access_key_id=credentials.access_key,
            aws_secret_access_key=credentials.secret_key,
            aws_session_token=credentials.session_token,
        )

    def read_secret(self, path: str) -> dict[str, Any] | str:
        response = self._aws_client.get_secret_value(SecretId=path)
        if 'SecretString' in response:
            payload = response['SecretString']
        else:
            payload = response['SecretBinary'].decode('utf-8')

        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            logging.debug("Secret payload is not JSON, returning payload as is")
            return payload

    def create_or_update_secret(self, path: str, data: dict):
        secret_string = json.dumps(data)
        try:
            self._aws_client.describe_secret(SecretId=path)
            logging.debug(f"Updating secret '{path}'...")
            response = self._aws_client.put_secret_value(SecretId=path, SecretString=secret_string)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == 'ResourceNotFoundException':
                logging.debug(f"Creating new secret '{path}'...")
                response = self._aws_client.create_secret(Name=path, SecretString=secret_string)
            else:
                raise e
        return response

    def delete_secret(self, path: str) -> dict[str, Any]:
        return self._aws_client.delete_secret(
            SecretId=path,
            ForceDeleteWithoutRecovery=True
        )

    def get_provider_name(self) -> str:
        return "aws_secrets_manager"
