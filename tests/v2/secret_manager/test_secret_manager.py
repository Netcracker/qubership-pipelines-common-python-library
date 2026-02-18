import pytest

from typing import Any
from qubership_pipelines_common_library.v2.secret_manager.model.secret_provider import SecretProvider
from qubership_pipelines_common_library.v2.secret_manager.secret_manager import SecretManager


class MockSecretProvider(SecretProvider):

    def __init__(self, initial_secrets: dict = None, **kwargs):
        super().__init__(**kwargs)
        self.secrets = {}
        if initial_secrets:
            self.secrets.update(initial_secrets)

    def read_secret(self, path: str) -> dict[str, Any] | str:
        if path in self.secrets:
            return self.secrets[path]
        else:
            raise Exception(f"Secret file {path} not found")

    def create_or_update_secret(self, path: str, data: dict):
        self.secrets[path] = data

    def delete_secret(self, path: str):
        self.secrets.pop(path, {})

    def get_provider_name(self) -> str:
        return "mock_secret_provider"


class TestSecretManager:

    def test_init_requires_provider(self):
        with pytest.raises(Exception) as ex:
            SecretManager(secret_provider=None)

        assert "Initialize SecretManager" in ex.value.args[0]

    def test_read_secrets(self):
        provider = MockSecretProvider(
            initial_secrets={
                "test/secret_str": "test_password1",
                "test/secret_dict": {"password": "test_password2"}
            }
        )
        secret_manager = SecretManager(secret_provider=provider)

        assert secret_manager.read_secret("test/secret_str") == "test_password1"
        assert secret_manager.read_secret("test/secret_dict").get("password") == "test_password2"
        with pytest.raises(Exception):
            secret_manager.read_secret("test/nonexistent_path")

    def test_create_and_update_secret(self):
        secret_manager = SecretManager(secret_provider=MockSecretProvider())
        secret_manager.create_or_update_secret("test/secret", {"password": "test_password"})
        assert secret_manager.read_secret("test/secret").get("password") == "test_password"
        secret_manager.create_or_update_secret("test/secret", {"password": "updated_test_password"})
        assert secret_manager.read_secret("test/secret").get("password") == "updated_test_password"

    def test_delete_secret(self):
        secret_manager = SecretManager(secret_provider=MockSecretProvider())
        secret_manager.create_or_update_secret("test/secret", {"password": "test_password"})
        assert secret_manager.read_secret("test/secret").get("password") == "test_password"

        secret_manager.delete_secret("test/secret")
        with pytest.raises(Exception):
            secret_manager.read_secret("test/secret")
