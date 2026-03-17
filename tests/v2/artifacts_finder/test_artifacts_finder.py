from pathlib import Path

import pytest
from unittest.mock import Mock, patch

from qubership_pipelines_common_library.v2.artifacts_finder.artifact_finder import ArtifactFinder
from qubership_pipelines_common_library.v2.artifacts_finder.auth.aws_credentials import AwsCredentialsProvider
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact import Artifact
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact_provider import ArtifactProvider
from qubership_pipelines_common_library.v2.artifacts_finder.providers.nexus import NexusProvider


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

    @patch('requests.sessions.Session.get')
    def test_nexus_search_snapshot_resolution(self, requests_mock):
        def side_effect(url, **kwargs):
            mock_resp = Mock()
            mock_resp.status_code = 200
            if url.endswith('/service/rest/v1/search/assets'):
                mock_resp.json.return_value = {
                    "items": [
                        {"downloadUrl": "https://mock.nexus.url/test-repo/org/qubership/test-component/0.5.0-SNAPSHOT/test-component-0.5.0-20260318.111111-1.pyz"},
                        {"downloadUrl": "https://mock.nexus.url/test-repo/org/qubership/test-component/0.5.0-SNAPSHOT/test-component-0.5.0-20260318.222222-2.pyz"},
                        {"downloadUrl": "https://mock.nexus.url/test-repo/org/qubership/test-component/0.5.0-SNAPSHOT/test-component-0.5.0-20260318.333333-3.pyz"},
                    ]
                }
            elif url.endswith('/maven-metadata.xml'):
                mock_resp.content = "<metadata><versioning><snapshot><timestamp>20260318.333333</timestamp><buildNumber>3</buildNumber></snapshot></versioning></metadata>"
            return mock_resp

        requests_mock.side_effect = side_effect
        artifact = Artifact(artifact_id="test-component", version="0.5.0-SNAPSHOT", extension="pyz")
        finder = ArtifactFinder(artifact_provider=NexusProvider(registry_url="https://mock.nexus.url"))

        urls = finder.find_artifact_urls(artifact=artifact)

        assert len(urls) == 1
        assert urls[0].rsplit("/", maxsplit=1)[-1] == "test-component-0.5.0-20260318.333333-3.pyz"
