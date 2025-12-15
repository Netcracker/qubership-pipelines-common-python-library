from pathlib import Path

import pytest
from unittest.mock import Mock, patch

from qubership_pipelines_common_library.v2.artifacts_finder.artifact_finder import ArtifactFinder
from qubership_pipelines_common_library.v2.artifacts_finder.auth.aws_credentials import AwsCredentialsProvider
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact import Artifact
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact_provider import ArtifactProvider


class TestArtifactFinder:

    def test_search_fails_without_required_params(self):
        artifact = Artifact(artifact_id="test-component")
        provider = Mock(spec=ArtifactProvider)
        finder = ArtifactFinder(artifact_provider=provider)

        with pytest.raises(Exception) as ex:
            finder.find_artifact_urls(artifact=artifact)

        assert "'version' must be specified" in ex.value.args[0]

    def test_search_is_invoked_in_provider(self):
        artifact = Artifact(artifact_id="test-component", version="1.0.0")
        provider = Mock(spec=ArtifactProvider)
        provider.search_artifacts.return_value = ["test_resource_url"]
        finder = ArtifactFinder(artifact_provider=provider)

        urls = finder.find_artifact_urls(artifact=artifact)

        assert len(urls) == 1
        assert urls[0] == "test_resource_url"

    def test_download_succeeds(self, tmp_path):
        artifact = Artifact(artifact_id="test-component", version="1.0.0", extension="json")
        provider = Mock(spec=ArtifactProvider)
        provider.search_artifacts.return_value = ["test_resource_url"]
        finder = ArtifactFinder(artifact_provider=provider)
        resource_url = "test_resource_url"

        finder.download_artifact(resource_url, tmp_path, artifact)
        provider.download_artifact.assert_called_once_with(
            resource_url=resource_url,
            local_path=Path(tmp_path).joinpath("test-component-1.0.0.json")
        )

    def test_credentials_provider_missing_auth_type(self):
        cred_provider = AwsCredentialsProvider()
        with pytest.raises(ValueError) as ex:
            cred_provider.get_credentials()
        assert "Need to initialize this provider with AuthType" in ex.value.args[0]

    @patch('boto3.client')
    def test_credentials_provider_contract(self, boto_client_mock):
        sts_client = Mock()
        boto_client_mock.return_value = sts_client
        sts_client.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "test_assumed_access_key",
                "SecretAccessKey": "test_assumed_secret_key",
                "SessionToken": "test_assumed_session_key",
            }
        }
        cred_provider = AwsCredentialsProvider().with_assume_role(
            access_key="test_access_key",
            secret_key="test_secret_key",
            region_name="eu-west",
            role_arn="test_role_arn",
        )
        credentials = cred_provider.get_credentials()
        assert credentials.access_key == "test_assumed_access_key"
        assert credentials.secret_key == "test_assumed_secret_key"
