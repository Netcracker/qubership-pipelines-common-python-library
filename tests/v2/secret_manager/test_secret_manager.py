import pytest
import os

from unittest.mock import MagicMock, patch
from qubership_pipelines_common_library.v2.artifacts_finder.auth.hashicorp_vault_credentials import HashicorpVaultCredentialsProvider
from qubership_pipelines_common_library.v2.artifacts_finder.model.credentials import Credentials
from qubership_pipelines_common_library.v2.secret_manager.model.secret_provider import SecretProvider
from qubership_pipelines_common_library.v2.secret_manager.providers.hashicorp_vault import HashicorpVaultProvider
from qubership_pipelines_common_library.v2.secret_manager.secret_manager import SecretManager
from qubership_pipelines_common_library.v2.secret_manager.providers.multi_store_provider import MultiStoreProvider


class MockSecretProvider(SecretProvider):
    def __init__(self, name="mock_provider", read_return=None, create_return=None,
                 update_return=None, delete_return=None):
        self.name = name
        self.read_return = read_return
        self.create_return = create_return
        self.update_return = update_return
        self.delete_return = delete_return
        self.read_called_with = None
        self.create_called_with = None
        self.update_called_with = None
        self.delete_called_with = None

    def read_secret(self, path: str):
        self.read_called_with = path
        if isinstance(self.read_return, Exception):
            raise self.read_return
        return self.read_return

    def create_secret(self, path: str, data: dict):
        self.create_called_with = (path, data)
        if isinstance(self.create_return, Exception):
            raise self.create_return
        return self.create_return

    def update_secret(self, path: str, data: dict):
        self.update_called_with = (path, data)
        if isinstance(self.update_return, Exception):
            raise self.update_return
        return self.update_return

    def delete_secret(self, path: str):
        self.delete_called_with = path
        if isinstance(self.delete_return, Exception):
            raise self.delete_return
        return self.delete_return

    def get_provider_name(self) -> str:
        return self.name


class TestSecretManager:
    def test_init_raises_without_provider(self):
        with pytest.raises(Exception, match="Initialize SecretManager"):
            SecretManager(secret_provider=None)

    def test_read_secret_success(self):
        mock_prov = MockSecretProvider(read_return="my-secret")
        sm = SecretManager(secret_provider=mock_prov)
        result = sm.read_secret("path/to/secret")
        assert result == "my-secret"
        assert mock_prov.read_called_with == "path/to/secret"

    def test_read_secret_provider_raises_not_fail_on_missing(self):
        mock_prov = MockSecretProvider(read_return=Exception("boom"))
        sm = SecretManager(secret_provider=mock_prov)
        result = sm.read_secret("path", fail_on_missing=False, default_value="default")
        assert result == "default"

    def test_read_secret_provider_raises_fail_on_missing(self):
        mock_prov = MockSecretProvider(read_return=Exception("boom"))
        sm = SecretManager(secret_provider=mock_prov)
        with pytest.raises(Exception, match="No secret found for path path"):
            sm.read_secret("path", fail_on_missing=True)

    def test_read_secret_returns_default_when_none(self):
        mock_prov = MockSecretProvider(read_return=None)
        sm = SecretManager(secret_provider=mock_prov)
        result = sm.read_secret("path", default_value=42)
        assert result == 42

    def test_read_secret_returns_none_when_default_not_given(self):
        mock_prov = MockSecretProvider(read_return=None)
        sm = SecretManager(secret_provider=mock_prov)
        result = sm.read_secret("path")
        assert result is None

    def test_create_secret(self):
        mock_prov = MockSecretProvider(create_return="created")
        sm = SecretManager(secret_provider=mock_prov)
        result = sm.create_secret("path", {"key": "val"})
        assert result == "created"
        assert mock_prov.create_called_with == ("path", {"key": "val"})

    def test_update_secret(self):
        mock_prov = MockSecretProvider(update_return="updated")
        sm = SecretManager(secret_provider=mock_prov)
        result = sm.update_secret("path", {"key": "new_val"})
        assert result == "updated"
        assert mock_prov.update_called_with == ("path", {"key": "new_val"})

    def test_delete_secret(self):
        mock_prov = MockSecretProvider(delete_return="deleted")
        sm = SecretManager(secret_provider=mock_prov)
        result = sm.delete_secret("path")
        assert result == "deleted"
        assert mock_prov.delete_called_with == "path"


@pytest.fixture
def mock_hvac_client():
    client = MagicMock()
    client.is_authenticated.return_value = True

    def mount_read_side_effect(path):
        if path.startswith("sys/internal/ui/mounts/"):
            rest = path.split("sys/internal/ui/mounts/", 1)[1]
            mount_name = rest.split("/", 1)[0]
            mount_path = mount_name + "/"
            version = "2" if "v2" in mount_name else "1"
            return {
                "data": {
                    "path": mount_path,
                    "options": {"version": version}
                }
            }
        return {}
    client.read.side_effect = mount_read_side_effect

    client.secrets.kv.v1.read_secret.return_value = {"data": {}}
    client.secrets.kv.v1.create_or_update_secret.return_value = None
    client.secrets.kv.v1.delete_secret.return_value = None

    client.secrets.kv.v2.read_secret_version.return_value = {"data": {"data": {}}}
    client.secrets.kv.v2.create_or_update_secret.return_value = None
    client.secrets.kv.v2.delete_metadata_and_all_versions.return_value = None
    return client


class TestHashicorpVaultProvider:
    def test_init_with_token(self, mock_hvac_client):
        creds = Credentials(token="s.token")
        with patch("hvac.Client", return_value=mock_hvac_client):
            provider = HashicorpVaultProvider(url="http://vault", credentials=creds)
        assert provider._vault_client == mock_hvac_client
        mock_hvac_client.is_authenticated.assert_called_once()

    def test_init_missing_url_raises(self):
        creds = Credentials(token="t")
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(Exception, match="Vault Address must be provided"):
                HashicorpVaultProvider(credentials=creds)

    def test_init_missing_credentials_raises(self):
        with pytest.raises(Exception, match="Credentials object is mandatory"):
            HashicorpVaultProvider(url="http://vault")

    def test_init_invalid_credentials_raises(self):
        creds = Credentials()
        with pytest.raises(Exception, match="did not have any valid configurations"):
            HashicorpVaultProvider(url="http://vault", credentials=creds)

    def test_init_not_authenticated_raises(self, mock_hvac_client):
        mock_hvac_client.is_authenticated.return_value = False
        creds = Credentials(token="t")
        with patch("hvac.Client", return_value=mock_hvac_client):
            with pytest.raises(Exception, match="not authenticated"):
                HashicorpVaultProvider(url="http://vault", credentials=creds)

    def test_read_secret_kv1_no_fragment(self, mock_hvac_client):
        mock_hvac_client.secrets.kv.v1.read_secret.return_value = {"data": {"key": "value"}}
        creds = Credentials(token="t")
        with patch("hvac.Client", return_value=mock_hvac_client):
            provider = HashicorpVaultProvider(url="http://vault", credentials=creds)
        result = provider.read_secret("secret_v1/mysecret/key")
        assert result == "value"
        mock_hvac_client.read.assert_any_call("sys/internal/ui/mounts/secret_v1/mysecret")

    def test_read_secret_kv2_with_explicit_fragment(self, mock_hvac_client):
        mock_hvac_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"nested": {"deep": "42"}}}
        }
        creds = Credentials(token="t")
        with patch("hvac.Client", return_value=mock_hvac_client):
            provider = HashicorpVaultProvider(url="http://vault", credentials=creds)
        result = provider.read_secret("secret_v2/data#/nested/deep")
        assert result == "42"

    def test_read_secret_missing_returns_none(self, mock_hvac_client):
        from hvac.exceptions import InvalidPath
        mock_hvac_client.secrets.kv.v1.read_secret.side_effect = InvalidPath()
        creds = Credentials(token="t")
        with patch("hvac.Client", return_value=mock_hvac_client):
            provider = HashicorpVaultProvider(url="http://vault", credentials=creds)
        result = provider.read_secret("secret_v1/nonexistent")
        assert result is None

    def test_create_secret_kv1_success(self, mock_hvac_client):
        creds = Credentials(token="t")
        with patch("hvac.Client", return_value=mock_hvac_client):
            provider = HashicorpVaultProvider(url="http://vault", credentials=creds)
        mock_hvac_client.secrets.kv.v1.read_secret.side_effect = Exception("not found")
        provider.create_secret("secret_v1/newsecret", {"key": "val"})
        mock_hvac_client.secrets.kv.v1.create_or_update_secret.assert_called_once_with(
            path="newsecret", secret={"key": "val"}, mount_point="secret_v1/"
        )

    def test_create_secret_already_exists_raises(self, mock_hvac_client):
        mock_hvac_client.secrets.kv.v1.read_secret.return_value = {"data": {"existing": "data"}}
        creds = Credentials(token="t")
        with patch("hvac.Client", return_value=mock_hvac_client):
            provider = HashicorpVaultProvider(url="http://vault", credentials=creds)
        with pytest.raises(Exception, match="already exists"):
            provider.create_secret("secret_v1/existing", {"key": "val"})

    def test_create_secret_fragment_not_allowed(self, mock_hvac_client):
        creds = Credentials(token="t")
        with patch("hvac.Client", return_value=mock_hvac_client):
            provider = HashicorpVaultProvider(url="http://vault", credentials=creds)
        with pytest.raises(ValueError, match="Fragment"):
            provider.create_secret("secret_v1/path#/key", {"a": 1})

    def test_update_secret_full_dict_kv2(self, mock_hvac_client):
        mock_hvac_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"original": "data", "old": "value"}}
        }
        creds = Credentials(token="t")
        with patch("hvac.Client", return_value=mock_hvac_client):
            provider = HashicorpVaultProvider(url="http://vault", credentials=creds)
        provider.update_secret("secret_v2/mysecret", {"new": "value"})
        mock_hvac_client.secrets.kv.v2.create_or_update_secret.assert_called_once()
        args = mock_hvac_client.secrets.kv.v2.create_or_update_secret.call_args[1]
        assert args["path"] == "mysecret"
        assert args["secret"] == {"original": "data", "old": "value", "new": "value"}

    def test_update_secret_fragment(self, mock_hvac_client):
        mock_hvac_client.secrets.kv.v1.read_secret.return_value = {
            "data": {"nested": {"deep": "old"}}
        }
        creds = Credentials(token="t")
        with patch("hvac.Client", return_value=mock_hvac_client):
            provider = HashicorpVaultProvider(url="http://vault", credentials=creds)
        provider.update_secret("secret_v1/mysecret#/nested/deep", "new_val")
        mock_hvac_client.secrets.kv.v1.create_or_update_secret.assert_called_once_with(
            path="mysecret", secret={"nested": {"deep": "new_val"}}, mount_point="secret_v1/"
        )

    def test_update_secret_missing_secret_raises(self, mock_hvac_client):
        mock_hvac_client.secrets.kv.v1.read_secret.side_effect = Exception("not found")
        creds = Credentials(token="t")
        with patch("hvac.Client", return_value=mock_hvac_client):
            provider = HashicorpVaultProvider(url="http://vault", credentials=creds)
        with pytest.raises(Exception, match="not found"):
            provider.update_secret("secret_v1/nonexistent", {"a": 1})

    def test_delete_secret_full_kv1(self, mock_hvac_client):
        creds = Credentials(token="t")
        with patch("hvac.Client", return_value=mock_hvac_client):
            provider = HashicorpVaultProvider(url="http://vault", credentials=creds)
        provider.delete_secret("secret_v1/mysecret")
        mock_hvac_client.secrets.kv.v1.delete_secret.assert_called_once_with(
            path="mysecret", mount_point="secret_v1/"
        )

    def test_delete_secret_fragment(self, mock_hvac_client):
        mock_hvac_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"a": {"b": "c", "d": "e"}}}
        }
        creds = Credentials(token="t")
        with patch("hvac.Client", return_value=mock_hvac_client):
            provider = HashicorpVaultProvider(url="http://vault", credentials=creds)
        provider.delete_secret("secret_v2/data#/a/b")
        mock_hvac_client.secrets.kv.v2.create_or_update_secret.assert_called_once_with(
            path="data", secret={"a": {"d": "e"}}, mount_point="secret_v2/"
        )

    def test_delete_secret_fragment_missing_key(self, mock_hvac_client):
        mock_hvac_client.secrets.kv.v1.read_secret.return_value = {"data": {"x": 1}}
        creds = Credentials(token="t")
        with patch("hvac.Client", return_value=mock_hvac_client):
            provider = HashicorpVaultProvider(url="http://vault", credentials=creds)
        with pytest.raises(Exception, match="not found"):
            provider.delete_secret("secret_v1/path#/nonexistent")


class TestHashicorpVaultCredentialsProvider:
    def test_with_env_vars_token(self):
        with patch.dict(os.environ, {"VAULT_TOKEN": "env-token"}, clear=True):
            prov = HashicorpVaultCredentialsProvider().with_env_vars()
            creds = prov.get_credentials()
            assert creds.token == "env-token"
            assert prov._auth_type == HashicorpVaultCredentialsProvider.AuthType.TOKEN

    def test_with_env_vars_userpass(self):
        with patch.dict(os.environ, {"VAULT_USERNAME": "env-user", "VAULT_PASSWORD": "env-pass"}, clear=True):
            prov = HashicorpVaultCredentialsProvider().with_env_vars()
            creds = prov.get_credentials()
            assert creds.username == "env-user"
            assert creds.password == "env-pass"
            assert prov._auth_type == HashicorpVaultCredentialsProvider.AuthType.USERPASS

    def test_with_env_vars_missing_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Could not find required environment variables"):
                HashicorpVaultCredentialsProvider().with_env_vars()

    def test_get_credentials_without_init_raises(self):
        with pytest.raises(ValueError, match="Need to initialize"):
            HashicorpVaultCredentialsProvider().get_credentials()


class TestMultiStoreProvider:

    def test_create_secret_not_implemented(self):
        with pytest.raises(NotImplementedError, match="MultiStoreProvider can only read secrets!"):
            MultiStoreProvider().create_secret("path", {})

    def test_read_secret_parses_uri_and_delegates(self):
        p = MultiStoreProvider()
        p._parse_uri = MagicMock(return_value=("vault", None))
        inner = MagicMock()
        inner.read_secret.return_value = "secret-value"
        p._build_provider = MagicMock(return_value=inner)

        result = p.read_secret("ref+vault://path/to/secret")

        assert result == "secret-value"
        p._parse_uri.assert_called_once_with("ref+vault://path/to/secret")
        p._build_provider.assert_called_once_with("vault", None)
        inner.read_secret.assert_called_once_with("ref+vault://path/to/secret")

    def test_read_secret_caches_provider_by_key(self):
        p = MultiStoreProvider()
        p._parse_uri = MagicMock(return_value=("vault", "store1"))
        inner = MagicMock()
        inner.read_secret.return_value = "val"
        p._build_provider = MagicMock(return_value=inner)

        p.read_secret("ref+vault://path1?secret_store_id=store1")
        p.read_secret("ref+vault://path2?secret_store_id=store1")

        p._build_provider.assert_called_once_with("vault", "store1")

    def test_read_secret_different_store_ids_new_provider(self):
        p = MultiStoreProvider()
        inner1 = MagicMock()
        inner1.read_secret.return_value = "val1"
        inner2 = MagicMock()
        inner2.read_secret.return_value = "val2"
        p._build_provider = MagicMock(side_effect=[inner1, inner2])

        assert p.read_secret("ref+vault://path1?secret_store_id=store1") == "val1"
        assert p.read_secret("ref+vault://path2?secret_store_id=store2") == "val2"
        assert p._build_provider.call_count == 2


class TestParseUri:

    def test_invalid_scheme_no_plus_raises(self):
        p = MultiStoreProvider()
        with pytest.raises(ValueError, match="Invalid VALS URI scheme"):
            p._parse_uri("novault://path")

    def test_unknown_provider_type_raises(self):
        p = MultiStoreProvider()
        with pytest.raises(ValueError, match="Unknown provider type"):
            p._parse_uri("ref+unknown://path")

    def test_without_store_id(self):
        p = MultiStoreProvider()
        assert p._parse_uri("ref+vault://secret/path") == ("vault", None)

    def test_with_store_id(self):
        p = MultiStoreProvider()
        assert p._parse_uri("ref+vault://path?secret_store_id=myid") == ("vault", "myid")

    def test_with_multiple_query_params(self):
        p = MultiStoreProvider()
        result = p._parse_uri("ref+awssecrets://path?foo=bar&secret_store_id=s1&baz=qux")
        assert result == ("awssecrets", "s1")
