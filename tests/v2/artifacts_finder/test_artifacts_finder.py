from pathlib import Path

import pytest
from unittest.mock import Mock, patch

from qubership_pipelines_common_library.v2.artifacts_finder.artifact_finder import ArtifactFinder
from qubership_pipelines_common_library.v2.artifacts_finder.auth.aws_credentials import AwsCredentialsProvider
from qubership_pipelines_common_library.v2.artifacts_finder.comparers.default_version_comparer import DefaultVersionComparer
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact import Artifact
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact_provider import ArtifactProvider
from qubership_pipelines_common_library.v2.artifacts_finder.model.credentials import Credentials
from qubership_pipelines_common_library.v2.artifacts_finder.providers.artifactory import ArtifactoryProvider
from qubership_pipelines_common_library.v2.artifacts_finder.providers.azure_artifacts import AzureArtifactsProvider
from qubership_pipelines_common_library.v2.artifacts_finder.providers.gcp_artifact_registry import GcpArtifactRegistryProvider
from qubership_pipelines_common_library.v2.artifacts_finder.providers.nexus import NexusProvider
from qubership_pipelines_common_library.v2.artifacts_finder.utils.artifact_finder_utils import ArtifactFinderUtils


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

    def test_select_latest_returns_payload_of_greatest_comparable(self):
        comparer = DefaultVersionComparer()
        candidates = [("1.0.0", "url-a"), ("2.0.0", "url-b"), ("1.5.0", "url-c")]
        assert ArtifactFinderUtils.select_latest(candidates, comparer) == "url-b"
        assert ArtifactFinderUtils.select_latest([], comparer) is None

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

    @patch('requests.sessions.Session.get')
    def test_artifactory_version_wildcard_search(self, requests_mock):
        base = "http://mock.artifactory/artifactory/libs-release-local/com/example/test-component"

        def result(version, ext):
            return {
                "downloadUri": f"{base}/{version}/test-component-{version}.{ext}",
                "ext": ext,
                "version": version,
            }

        def side_effect(url, **kwargs):
            mock_resp = Mock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"results": [
                result("master-5.0.0-20260101.120000-RELEASE", "yaml"),
                result("master-5.0.1-20260201.130000-RELEASE", "yaml"),
                result("master-6.0.0-20260301.140000-RELEASE", "yaml"),
                result("master-5.0.0-20260101.120000-RELEASE", "json"),
            ]}
            return mock_resp

        requests_mock.side_effect = side_effect
        finder = ArtifactFinder(artifact_provider=ArtifactoryProvider(
            registry_url="http://mock.artifactory/artifactory", username="admin", password="Password1"))

        urls = finder.find_artifact_urls(artifact_id="test-component", version="master-*-RELEASE", extension="yaml")
        assert len(urls) == 3
        assert all(url.endswith(".yaml") for url in urls)

        latest = finder.find_artifact_urls(artifact_id="test-component", version="master-*-RELEASE",
                                           extension="yaml", latest=True)
        assert latest == [f"{base}/master-6.0.0-20260301.140000-RELEASE/test-component-master-6.0.0-20260301.140000-RELEASE.yaml"]

    @patch('requests.sessions.Session.get')
    def test_nexus_version_wildcard_search_paginated(self, requests_mock):
        base = "https://mock.nexus.url/repository/test-mvn/com/sometest/group2/light-config"

        def asset(version, ext="yaml"):
            return {
                "downloadUrl": f"{base}/{version}/light-config-{version}.{ext}",
                "maven2": {"artifactId": "light-config", "extension": ext, "version": version},
            }

        page1 = [asset("master-5.0.0-RELEASE"), asset("master-5.0.1-RELEASE")]
        page2 = [asset("master-6.0.0-RELEASE"), asset("master-6.0.0-DEV")]

        def side_effect(url, **kwargs):
            params = kwargs.get("params", {})
            mock_resp = Mock()
            mock_resp.status_code = 200
            if params.get("continuationToken") == "TOKEN":
                mock_resp.json.return_value = {"items": page2, "continuationToken": None}
            else:
                mock_resp.json.return_value = {"items": page1, "continuationToken": "TOKEN"}
            return mock_resp

        requests_mock.side_effect = side_effect
        finder = ArtifactFinder(artifact_provider=NexusProvider(registry_url="https://mock.nexus.url"))

        urls = finder.find_artifact_urls(artifact_id="light-config", version="master-*-RELEASE", extension="yaml")
        assert len(urls) == 3

        latest = finder.find_artifact_urls(artifact_id="light-config", version="master-*-RELEASE",
                                           extension="yaml", latest=True)
        assert latest == [f"{base}/master-6.0.0-RELEASE/light-config-master-6.0.0-RELEASE.yaml"]

    @patch('requests.sessions.Session.get')
    def test_azure_version_wildcard_search(self, requests_mock):
        org, project, feed_id = "myorg", "myproj", "MYFEEDID"
        versions_url = f"https://feeds.dev.azure.com/{org}/{project}/_apis/packaging/feeds/{feed_id}/packages/PKGID/versions"

        def version_entry(v):
            return {
                "version": v,
                "protocolMetadata": {"data": {"version": v, "groupId": "com.example", "artifactId": "test-component"}},
                "files": [{"name": f"test-component-{v}.yaml"}, {"name": "test-component.pom"}],
            }

        all_versions = [
            version_entry("master-5.0.0-RELEASE"), version_entry("master-5.0.1-RELEASE"),
            version_entry("master-6.0.0-RELEASE"), version_entry("dev-1.0.0-RELEASE"),
        ]

        def side_effect(url, **kwargs):
            mock_resp = Mock()
            mock_resp.status_code = 200
            if url == versions_url:
                mock_resp.json.return_value = {"value": all_versions}
            else:
                mock_resp.json.return_value = {"value": [{"_links": {
                    "versions": {"href": versions_url},
                    "feed": {"href": f"https://feeds.dev.azure.com/{org}/{project}/_apis/packaging/feeds/{feed_id}"},
                }}]}
            return mock_resp

        requests_mock.side_effect = side_effect
        finder = ArtifactFinder(artifact_provider=AzureArtifactsProvider(
            credentials=Credentials(access_token="token"), organization=org, project=project, feed="myfeed"))

        def expected_url(v):
            return (f"https://pkgs.dev.azure.com/{org}/{project}/_apis/packaging/feeds/{feed_id}/maven/"
                    f"com.example/test-component/{v}/test-component-{v}.yaml/content?api-version=7.1-preview.1")

        urls = finder.find_artifact_urls(artifact_id="test-component", version="master-*-RELEASE", extension="yaml")
        assert urls == [
            expected_url("master-5.0.0-RELEASE"),
            expected_url("master-5.0.1-RELEASE"),
            expected_url("master-6.0.0-RELEASE"),
        ]

        latest = finder.find_artifact_urls(artifact_id="test-component", version="master-*-RELEASE",
                                           extension="yaml", latest=True)
        assert latest == [expected_url("master-6.0.0-RELEASE")]

    @patch('google.cloud.artifactregistry_v1.ArtifactRegistryClient')
    def test_gcp_version_wildcard_search(self, gcp_client_cls):
        repo = "projects/proj/locations/us/repositories/repo"

        def gcp_file(version):
            encoded = f"com%2Fexample%2Ftest-component%2F{version}%2Ftest-component-{version}.yaml"
            from types import SimpleNamespace
            return SimpleNamespace(name=f"{repo}/files/{encoded}")

        gcp_client = Mock()
        gcp_client_cls.return_value = gcp_client
        gcp_client.list_files.return_value = [
            gcp_file("master-5.0.0-RELEASE"), gcp_file("master-5.0.1-RELEASE"),
            gcp_file("master-6.0.0-RELEASE"), gcp_file("dev-1.0.0-RELEASE"),
        ]

        finder = ArtifactFinder(artifact_provider=GcpArtifactRegistryProvider(
            credentials=Credentials(google_credentials_object=Mock(), authorized_session=Mock()),
            project="proj", region_name="us", repository="repo"))

        def expected_url(version):
            encoded = f"com%2Fexample%2Ftest-component%2F{version}%2Ftest-component-{version}.yaml"
            return f"https://artifactregistry.googleapis.com/download/v1/{repo}/files/{encoded}:download?alt=media"

        urls = finder.find_artifact_urls(artifact_id="test-component", version="master-*-RELEASE", extension="yaml")
        assert urls == [
            expected_url("master-5.0.0-RELEASE"),
            expected_url("master-5.0.1-RELEASE"),
            expected_url("master-6.0.0-RELEASE"),
        ]

        sent_filter = gcp_client.list_files.call_args.kwargs["request"].filter
        assert sent_filter == f'name="{repo}/files/*test-component-master-*"'

        latest = finder.find_artifact_urls(artifact_id="test-component", version="master-*-RELEASE",
                                           extension="yaml", latest=True)
        assert latest == [expected_url("master-6.0.0-RELEASE")]
