import json
import boto3
import yaml

from botocore.config import Config
from botocore.exceptions import ClientError
from typing import Any
from qubership_pipelines_common_library.v1.utils.utils import recursive_merge
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

    def read_secret(self, path: str) -> str | None:
        secret_path, frag = self.parse_vals_path(path)
        payload = self._get_secret_payload(secret_path)

        if payload is None:
            return None
        if not frag:
            return payload

        data = self._payload_to_dict(payload)
        secret_value = self.get_frag_value(data, frag)
        if secret_value is not None and not isinstance(secret_value, str):
            secret_value = str(secret_value)
        return secret_value

    def create_secret(self, path: str, data: Any):
        secret_path, frag = self.parse_vals_path(path)
        if frag is not None:
            raise ValueError("Fragment (#/key) in path is not allowed when creating a secret")

        if isinstance(data, dict):
            secret_string = json.dumps(data)
        elif isinstance(data, str):
            secret_string = data
        else:
            secret_string = str(data)

        if self._secret_exists(secret_path):
            raise Exception(f"Secret at path '{path}' already exists")

        return self._aws_client.create_secret(Name=secret_path, SecretString=secret_string)

    def update_secret(self, path: str, data: Any):
        secret_path, fragment = self.parse_vals_path(path)
        payload = self._get_secret_payload(secret_path)
        if payload is None:
            raise Exception(f"Secret to update not found at path '{path}'")
        try:
            current_data = yaml.safe_load(payload)
        except yaml.YAMLError:
            current_data = payload

        if fragment is not None:
            if not isinstance(current_data, dict):
                raise ValueError("Secret payload is not a mapping; cannot apply fragment")
            if self.is_non_scalar(data):
                raise ValueError("When updating a fragment, data must be a non-dict (string) value")
            updated_data = self.set_frag_value(current_data, fragment, data)
        else:
            if isinstance(data, dict) and isinstance(current_data, dict):
                updated_data = recursive_merge(current_data, data)
            elif isinstance(data, str) and isinstance(current_data, str):
                updated_data = data
            else:
                raise ValueError("Cannot overwrite a complex secret with a single value")

        return self._aws_client.put_secret_value(SecretId=secret_path, SecretString=json.dumps(updated_data))

    def delete_secret(self, path: str):
        secret_path, fragment = self.parse_vals_path(path)
        if fragment:
            payload = self._get_secret_payload(secret_path)
            if payload is None:
                raise Exception(f"Secret to delete not found at path '{path}'")
            current_data = self._payload_to_dict(payload)
            updated_data = self.delete_frag_value(current_data, fragment)
            new_payload = json.dumps(updated_data)
            return self._aws_client.put_secret_value(SecretId=secret_path, SecretString=new_payload)
        else:
            return self._aws_client.delete_secret(SecretId=secret_path, ForceDeleteWithoutRecovery=True)

    def get_provider_name(self) -> str:
        return "awssecrets"

    def secret_exists(self, path: str) -> bool:
        secret_path, _ = self.parse_vals_path(path)
        return self._secret_exists(secret_path)

    def _secret_exists(self, secret_id: str) -> bool:
        try:
            self._aws_client.describe_secret(SecretId=secret_id)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                return False
            raise

    def _get_secret_payload(self, secret_id: str) -> str | None:
        try:
            response = self._aws_client.get_secret_value(SecretId=secret_id)
            if 'SecretString' in response:
                payload = response['SecretString']
            else:
                payload = response['SecretBinary'].decode('utf-8')
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == 'ResourceNotFoundException':
                return None
            raise
        return payload

    @staticmethod
    def _payload_to_dict(payload: str) -> dict:
        try:
            current_data = yaml.safe_load(payload)
        except yaml.YAMLError:
            raise ValueError("Secret payload could not be unmarshalled as YAML/JSON")
        if not isinstance(current_data, dict):
            raise ValueError("Secret payload is not a mapping; cannot apply fragment")
        return current_data
