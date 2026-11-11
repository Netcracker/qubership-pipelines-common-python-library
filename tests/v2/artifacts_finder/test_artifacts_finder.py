from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
from google.cloud import artifactregistry_v1
from unittest.mock import Mock, patch

from qubership_pipelines_common_library.v2.artifacts_finder.artifact_finder import ArtifactFinder
from qubership_pipelines_common_library.v2.artifacts_finder.auth.aws_credentials import AwsCredentialsProvider
from qubership_pipelines_common_library.v2.artifacts_finder.comparers.default_version_comparer import DefaultVersionComparer
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact import Artifact
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact_provider import (
    ArtifactProvider,
    ArtifactProviderError,
    ArtifactSearchResult,
)
from qubership_pipelines_common_library.v2.artifacts_finder.model.credentials import Credentials
from qubership_pipelines_common_library.v2.artifacts_finder.providers.artifactory import ArtifactoryProvider
from qubership_pipelines_common_library.v2.artifacts_finder.providers.azure_artifacts import AzureArtifactsProvider
from qubership_pipelines_common_library.v2.artifacts_finder.providers.gcp_artifact_registry import GcpArtifactRegistryProvider
from qubership_pipelines_common_library.v2.artifacts_finder.providers.nexus import NexusProvider
from qubership_pipelines_common_library.v2.artifacts_finder.providers.multi_artifact_provider import MultiArtifactProvider
from qubership_pipelines_common_library.v2.artifacts_finder.utils.artifact_finder_utils import ArtifactFinderUtils, ArtifactProviderFactory


class TestArtifactFinder:

    def test_command_factory_passes_max_retries_to_provider(self):
        cmd = Mock()
        cmd.context.input_param_get.return_value = {
            "nexus": {"registry_url": "https://nexus.example", "max_retries": 2},
        }
        cmd.timeout_seconds = 300
        cmd.verify = True

        finder = ArtifactFinderUtils.create_artifact_finder_for_command(cmd)

        assert finder.provider._max_retries == 2

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
        provider.search_artifacts.return_value = ArtifactSearchResult(urls=["test_resource_url"])
        finder = ArtifactFinder(artifact_provider=provider)

        urls = finder.find_artifact_urls(artifact=artifact)

        assert len(urls) == 1
        assert urls[0] == "test_resource_url"

    def test_download_succeeds(self, tmp_path):
        artifact = Artifact(artifact_id="test-component", version="1.0.0", extension="json")
        provider = Mock(spec=ArtifactProvider)
        provider.search_artifacts.return_value = ArtifactSearchResult(urls=["test_resource_url"])
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
    def test_nexus_short_wildcard_prefix_omits_server_version(self, requests_mock):
        base = "https://mock.nexus.url/repository/test-mvn/com/example/bulk-snap-wild"
        sent_params = []

        def side_effect(url, **kwargs):
            sent_params.append(kwargs.get("params", {}))
            mock_resp = Mock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"items": [
                {"downloadUrl": f"{base}/1.0.0-SNAPSHOT/bulk-snap-wild-1.0.0-20261029.061926-1.json",
                 "maven2": {"version": "1.0.0-20261029.061926-1"}},
            ], "continuationToken": None}
            return mock_resp

        requests_mock.side_effect = side_effect
        finder = ArtifactFinder(artifact_provider=NexusProvider(registry_url="https://mock.nexus.url"))

        urls = finder.find_artifact_urls(artifact_id="bulk-snap-wild", version="1.*", extension="json")

        assert urls == [f"{base}/1.0.0-SNAPSHOT/bulk-snap-wild-1.0.0-20261029.061926-1.json"]
        assert "version" not in sent_params[0]

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

    @patch('google.cloud.artifactregistry_v1.ArtifactRegistryClient')
    def test_gcp_virtual_repository_searches_upstreams(self, gcp_client_cls):
        repository = artifactregistry_v1.Repository
        virtual_repo = "projects/proj/locations/us/repositories/virtual-repo"
        nested_repo = "projects/proj/locations/us/repositories/nested-repo"
        upstream_a = "projects/proj/locations/us/repositories/upstream-a"
        upstream_b = "projects/proj/locations/us/repositories/upstream-b"

        def repository_config(mode, repository_format=repository.Format.MAVEN, upstreams=()):
            return SimpleNamespace(
                mode=mode,
                format=repository_format,
                virtual_repository_config=SimpleNamespace(upstream_policies=[SimpleNamespace(repository=name, priority=priority) for name, priority in upstreams]),
            )

        configs = {
            virtual_repo: repository_config(repository.Mode.VIRTUAL_REPOSITORY, upstreams=[(nested_repo, 100), (upstream_b, 50)]),
            nested_repo: repository_config(repository.Mode.VIRTUAL_REPOSITORY, upstreams=[(upstream_a, 10)]),
            upstream_a: repository_config(repository.Mode.STANDARD_REPOSITORY),
            upstream_b: repository_config(repository.Mode.STANDARD_REPOSITORY),
        }

        def artifact_file(parent, version):
            encoded = f"com%2Fexample%2Ftest-component%2F{version}%2Ftest-component-{version}.yaml"
            return SimpleNamespace(name=f"{parent}/files/{encoded}")

        gcp_client = Mock()
        gcp_client_cls.return_value = gcp_client
        gcp_client.get_repository.side_effect = lambda name, **kwargs: configs[name]
        gcp_client.list_files.side_effect = lambda request, **kwargs: {
            upstream_a: [artifact_file(upstream_a, "1.0.0")],
            upstream_b: [artifact_file(upstream_b, "1.0.0"), artifact_file(upstream_b, "2.0.0")],
        }[request.parent]

        finder = ArtifactFinder(artifact_provider=GcpArtifactRegistryProvider(
            credentials=Credentials(google_credentials_object=Mock(), authorized_session=Mock()),
            project="proj", region_name="us", repository="virtual-repo"))

        def expected_url(version):
            return f"https://us-maven.pkg.dev/proj/virtual-repo/com/example/test-component/{version}/test-component-{version}.yaml"

        # upstreams are listed directly, but the same artifact found in several of them yields a single URL
        urls = finder.find_artifact_urls(artifact_id="test-component", version="*", extension="yaml")
        assert urls == [expected_url("1.0.0"), expected_url("2.0.0")]

        # upstreams are traversed by descending priority, non-virtual ones only, and only once each
        assert [call.kwargs["name"] for call in gcp_client.get_repository.call_args_list] == [
            virtual_repo, nested_repo, upstream_a, upstream_b,
        ]
        assert [call.kwargs["request"].parent for call in gcp_client.list_files.call_args_list] == [
            upstream_a, upstream_b,
        ]

        gcp_client.reset_mock()
        latest = finder.find_artifact_urls(artifact_id="test-component", version="*", extension="yaml", latest=True)
        assert latest == [expected_url("2.0.0")]
        # upstreams of the configured repository are resolved once per provider instance
        gcp_client.get_repository.assert_not_called()
        assert gcp_client.list_files.call_count == 2

    @patch('google.cloud.artifactregistry_v1.ArtifactRegistryClient')
    def test_gcp_generic_repository_keeps_download_api_urls(self, gcp_client_cls):
        # generic repositories have no `pkg.dev` endpoint, so they are always addressed through the download API
        repository = artifactregistry_v1.Repository
        repo = "projects/proj/locations/us/repositories/generic-repo"
        encoded = "some_sd%2F16.0.2-RELEASE%2Fsome_sd-16.0.2-RELEASE.json"

        gcp_client = Mock()
        gcp_client_cls.return_value = gcp_client
        gcp_client.get_repository.return_value = SimpleNamespace(
            mode=repository.Mode.STANDARD_REPOSITORY,
            format=repository.Format.GENERIC,
            virtual_repository_config=None,
        )
        gcp_client.list_files.return_value = [SimpleNamespace(name=f"{repo}/files/{encoded}")]

        finder = ArtifactFinder(artifact_provider=GcpArtifactRegistryProvider(
            credentials=Credentials(google_credentials_object=Mock(), authorized_session=Mock()),
            project="proj", region_name="us", repository="generic-repo"))

        urls = finder.find_artifact_urls(artifact_id="some_sd", version="16.0.2-RELEASE", extension="json")

        assert urls == [f"https://artifactregistry.googleapis.com/download/v1/{repo}/files/{encoded}:download?alt=media"]

    @patch('google.cloud.artifactregistry_v1.ArtifactRegistryClient')
    def test_gcp_virtual_repository_with_unsupported_format(self, gcp_client_cls):
        # Artifact Registry supports virtual repositories for the maven format only
        repository = artifactregistry_v1.Repository
        virtual_repo = "projects/proj/locations/us/repositories/generic-virtual-repo"
        upstream = "projects/proj/locations/us/repositories/generic-repo"
        encoded = "some_sd%2F16.0.2-RELEASE%2Fsome_sd-16.0.2-RELEASE.json"

        gcp_client = Mock()
        gcp_client_cls.return_value = gcp_client
        gcp_client.get_repository.side_effect = lambda name, **kwargs: SimpleNamespace(
            mode=repository.Mode.VIRTUAL_REPOSITORY if name == virtual_repo else repository.Mode.STANDARD_REPOSITORY,
            format=repository.Format.GENERIC,
            virtual_repository_config=SimpleNamespace(upstream_policies=[SimpleNamespace(repository=upstream, priority=100)])
        )
        gcp_client.list_files.return_value = [SimpleNamespace(name=f"{upstream}/files/{encoded}")]

        finder = ArtifactFinder(artifact_provider=GcpArtifactRegistryProvider(
            credentials=Credentials(google_credentials_object=Mock(), authorized_session=Mock()),
            project="proj", region_name="us", repository="generic-virtual-repo"
        ))

        with pytest.raises(Exception) as ex:
            finder.find_artifact_urls(artifact_id="some_sd", version="16.0.2-RELEASE", extension="json")

        assert "can't be served by a virtual repository" in ex.value.args[0]

    @patch('qubership_pipelines_common_library.v2.artifacts_finder.providers.gcp_artifact_registry.AuthorizedSession')
    @patch('google.cloud.artifactregistry_v1.ArtifactRegistryClient')
    def test_gcp_virtual_repository_resolves_snapshot(self, gcp_client_cls, authorized_session_cls):
        repository = artifactregistry_v1.Repository
        virtual_repo = "projects/proj/locations/us/repositories/virtual-repo"
        upstream = "projects/proj/locations/us/repositories/upstream-repo"
        encoded = "com%2Fexample%2Ftest-component%2F1.0-SNAPSHOT%2Fmaven-metadata.xml"
        metadata = (b"<metadata><versioning><snapshot><timestamp>20250101.010203</timestamp>"
                    b"<buildNumber>1</buildNumber></snapshot></versioning></metadata>")

        authorized_session = Mock()
        authorized_session_cls.return_value = authorized_session
        metadata_response = Mock()
        metadata_response.status_code = 200
        metadata_response.content = metadata
        authorized_session.get.return_value = metadata_response

        gcp_client = Mock()
        gcp_client_cls.return_value = gcp_client
        gcp_client.get_repository.side_effect = lambda name, **kwargs: SimpleNamespace(
            mode=repository.Mode.VIRTUAL_REPOSITORY if name == virtual_repo else repository.Mode.STANDARD_REPOSITORY,
            format=repository.Format.MAVEN,
            virtual_repository_config=SimpleNamespace(upstream_policies=[SimpleNamespace(repository=upstream, priority=100)])
        )
        gcp_client.list_files.return_value = [SimpleNamespace(name=f"{upstream}/files/{encoded}")]

        finder = ArtifactFinder(artifact_provider=GcpArtifactRegistryProvider(
            credentials=Credentials(google_credentials_object=Mock(), authorized_session=authorized_session),
            project="proj", region_name="us", repository="virtual-repo"))

        urls = finder.find_artifact_urls(artifact_id="test-component", version="1.0-SNAPSHOT", extension="jar")

        assert urls == ["https://us-maven.pkg.dev/proj/virtual-repo/com/example/test-component/1.0-SNAPSHOT/test-component-1.0-20250101.010203-1.jar"]
        # maven-metadata.xml is also read through the virtual repository, not from its upstream
        authorized_session.get.assert_called_once_with(
            url="https://us-maven.pkg.dev/proj/virtual-repo/com/example/test-component/1.0-SNAPSHOT/maven-metadata.xml",
            timeout=None,
        )

    def test_deduplicate_keeps_original_order(self):
        assert ArtifactFinderUtils.deduplicate(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]
        assert ArtifactFinderUtils.deduplicate([]) == []


class TestMultipleProviders:

    @staticmethod
    def provider(name, urls=None, error=None):
        provider = Mock(spec=ArtifactProvider)
        provider.get_provider_name.return_value = name
        if error is not None:
            provider.search_artifacts.side_effect = error
        else:
            provider.search_artifacts.return_value = ArtifactSearchResult(urls=list(urls or []))
        return provider

    def test_constructor_wraps_provider_list_in_group(self):
        first, second = self.provider("first"), self.provider("second")

        finder = ArtifactFinder(artifact_provider=MultiArtifactProvider([first, second]))

        assert isinstance(finder.provider, MultiArtifactProvider)
        assert finder.provider.providers == [first, second]

    def test_first_non_empty_provider_wins(self):
        first = self.provider("first", ["https://first.example/demo.json"])
        second = self.provider("second", ["https://second.example/demo.json"])
        finder = ArtifactFinder(artifact_provider=MultiArtifactProvider([first, second]))

        urls = finder.find_artifact_urls(artifact_id="demo", version="1.0.0")

        assert urls == ["https://first.example/demo.json"]
        second.search_artifacts.assert_not_called()

    def test_empty_provider_falls_through(self):
        first = self.provider("first")
        second = self.provider("second", ["https://second.example/demo.json"])
        finder = ArtifactFinder(artifact_provider=MultiArtifactProvider([first, second]))

        urls = finder.find_artifact_urls(artifact_id="demo", version="1.0.0")

        assert urls == ["https://second.example/demo.json"]

    def test_failed_provider_falls_through(self):
        first = self.provider("first", error=RuntimeError("first exploded"))
        second = self.provider("second", ["https://second.example/demo.json"])
        finder = ArtifactFinder(artifact_provider=MultiArtifactProvider([first, second]))

        urls = finder.find_artifact_urls(artifact_id="demo", version="1.0.0")

        assert urls == ["https://second.example/demo.json"]

    def test_all_provider_errors_are_aggregated(self):
        first = self.provider("first", error=RuntimeError("first exploded"))
        second = self.provider("second", error=RuntimeError("second exploded"))
        finder = ArtifactFinder(artifact_provider=MultiArtifactProvider([first, second]))

        with pytest.raises(Exception) as ex:
            finder.find_artifact_urls(artifact_id="demo", version="1.0.0")

        message = str(ex.value)
        assert "- first: first exploded" in message
        assert "- second: second exploded" in message

    def test_all_empty_results_mean_not_found(self):
        finder = ArtifactFinder(artifact_provider=MultiArtifactProvider([self.provider("first"), self.provider("second")]))

        assert finder.find_artifact_urls(artifact_id="demo", version="1.0.0") == []

    def test_resolved_url_uses_cached_provider_for_download(self, tmp_path):
        first = self.provider("first")
        second = self.provider("second", ["https://second.example/demo.json"])
        finder = ArtifactFinder(artifact_provider=MultiArtifactProvider([first, second]))
        finder.find_artifact_urls(artifact_id="demo", version="1.0.0")

        finder.download_artifact("https://second.example/demo.json", tmp_path / "demo.json")

        second.download_artifact.assert_called_once()
        first.download_artifact.assert_not_called()

    def test_unknown_url_uses_first_provider_when_it_succeeds(self, tmp_path):
        first, second = self.provider("first"), self.provider("second")
        finder = ArtifactFinder(artifact_provider=MultiArtifactProvider([first, second]))

        finder.download_artifact("https://unknown.example/demo.json", tmp_path / "demo.json")

        first.download_artifact.assert_called_once()
        second.download_artifact.assert_not_called()

    def test_unknown_url_falls_through_to_next_provider(self, tmp_path):
        first, second = self.provider("first"), self.provider("second")
        first.download_artifact.side_effect = RuntimeError("first download failed")
        finder = ArtifactFinder(artifact_provider=MultiArtifactProvider([first, second]))

        finder.download_artifact("https://unknown.example/demo.json", tmp_path / "demo.json")

        first.download_artifact.assert_called_once()
        second.download_artifact.assert_called_once()

    def test_download_errors_are_aggregated_when_all_providers_fail(self, tmp_path):
        first, second = self.provider("first"), self.provider("second")
        first.download_artifact.side_effect = RuntimeError("first download failed")
        second.download_artifact.side_effect = RuntimeError("second download failed")
        finder = ArtifactFinder(artifact_provider=MultiArtifactProvider([first, second]))

        with pytest.raises(Exception) as ex:
            finder.download_artifact("https://unknown.example/demo.json", tmp_path / "demo.json")

        message = str(ex.value)
        assert "- first: first download failed" in message
        assert "- second: second download failed" in message

    def test_single_provider_download_uses_provider(self, tmp_path):
        provider = self.provider("only")
        finder = ArtifactFinder(artifact_provider=provider)

        finder.download_artifact("https://unknown.example/demo.json", tmp_path / "demo.json")

        provider.download_artifact.assert_called_once()


class TestErrorMessages:

    @patch('requests.sessions.Session.get')
    def test_artifactory_search_error_includes_request_url(self, session_get):
        response = Mock()
        response.status_code = 401
        response.reason = "Unauthorized"
        response.text = "denied"
        response.request = None
        session_get.return_value = response
        provider = ArtifactoryProvider(registry_url="http://mock.artifactory/artifactory")

        with pytest.raises(Exception) as ex:
            provider.search_artifacts(Artifact(group_id="com.example", artifact_id="demo", version="1.*"))

        message = str(ex.value)
        assert isinstance(ex.value, ArtifactProviderError)
        assert ex.value.status_code == 401
        assert "GET http://mock.artifactory/artifactory/api/search/gavc?" in message
        assert "a=demo" in message
        assert "HTTP 401 Unauthorized" in message
        assert "denied" in message

    @patch('requests.sessions.Session.get', side_effect=requests.ConnectionError("connection refused"))
    def test_artifactory_network_error_includes_request_url(self, _):
        provider = ArtifactoryProvider(registry_url="http://mock.artifactory/artifactory")

        with pytest.raises(Exception) as ex:
            provider.search_artifacts(Artifact(group_id="com.example", artifact_id="demo", version="1.*"))

        message = str(ex.value)
        assert "GET http://mock.artifactory/artifactory/api/search/gavc?" in message
        assert "failed: connection refused" in message

    @patch('requests.sessions.Session.get')
    def test_download_error_includes_request_url(self, session_get, tmp_path):
        response = Mock()
        response.status_code = 404
        response.reason = "Not Found"
        response.text = "missing"
        response.request = None
        session_get.return_value = response
        provider = ArtifactoryProvider(registry_url="http://mock.artifactory/artifactory")
        url = "http://mock.artifactory/artifactory/libs-release-local/x.json"

        with pytest.raises(Exception) as ex:
            provider.download_artifact(url, tmp_path / "x.json")

        message = str(ex.value)
        assert isinstance(ex.value, ArtifactProviderError)
        assert ex.value.status_code == 404
        assert f"GET {url} -> HTTP 404 Not Found" in message
        assert "missing" in message


class TestDirectUrlResolution:

    @staticmethod
    def _gavc_response(*versions):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"results": [
            {"downloadUri": f"https://search.example.com/{version}/demo-{version}.json",
             "ext": "json", "version": version}
            for version in versions
        ]}
        return response

    @staticmethod
    def _head(status_code=200, headers=None):
        response = Mock()
        response.status_code = status_code
        response.headers = headers or {}
        response.close = Mock()
        return response

    @staticmethod
    def _nexus_empty_search_response():
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"items": []}
        return response

    @patch('requests.sessions.Session.head')
    @patch('requests.sessions.Session.get')
    def test_provider_without_repositories_uses_search(self, session_get, session_head):
        session_get.return_value = self._gavc_response("1.0.0")
        finder = ArtifactFinder(artifact_provider=ArtifactoryProvider(
            registry_url="http://mock.artifactory/artifactory"))

        urls = finder.find_artifact_urls(group_id="com.example", artifact_id="demo",
                                         version="1.0.0", extension="json")

        assert urls == ["https://search.example.com/1.0.0/demo-1.0.0.json"]
        session_head.assert_not_called()

    @patch('requests.sessions.Session.head')
    @patch('requests.sessions.Session.get')
    def test_direct_resolution_requires_group_and_exact_version(self, session_get, session_head):
        session_get.return_value = self._gavc_response("1.0.0")
        finder = ArtifactFinder(artifact_provider=ArtifactoryProvider(
            registry_url="http://mock.artifactory/artifactory", repositories=["libs-release-local"]))

        finder.find_artifact_urls(artifact_id="demo", version="1.0.0", extension="json")
        finder.find_artifact_urls(group_id="com.example", artifact_id="demo", version="1.0.*", extension="json")

        session_head.assert_not_called()
        assert session_get.call_count == 2

    @patch('requests.sessions.Session.head')
    @patch('requests.sessions.Session.get')
    def test_artifactory_direct_url_release_hit(self, session_get, session_head):
        session_head.return_value = self._head()
        finder = ArtifactFinder(artifact_provider=ArtifactoryProvider(
            registry_url="http://mock.artifactory/artifactory", repositories=["libs-release-local"]))

        urls = finder.find_artifact_urls(group_id="com.example", artifact_id="demo",
                                         version="1.0.0", extension="json")

        assert urls == [
            "http://mock.artifactory/artifactory/libs-release-local/com/example/demo/1.0.0/demo-1.0.0.json"
        ]
        session_get.assert_not_called()
        session_head.assert_called_once_with(
            "http://mock.artifactory/artifactory/libs-release-local/com/example/demo/1.0.0/demo-1.0.0.json",
            timeout=None, allow_redirects=True,
        )

    @patch('requests.sessions.Session.head')
    def test_artifactory_search_reports_direct_method(self, session_head):
        session_head.return_value = self._head()
        provider = ArtifactoryProvider(
            registry_url="http://mock.artifactory/artifactory", repositories=["libs-release-local"])

        result = provider.search_artifacts(
            Artifact(group_id="com.example", artifact_id="demo", version="1.0.0", extension="json"))

        assert result.method == "direct"
        assert result.urls == [
            "http://mock.artifactory/artifactory/libs-release-local/com/example/demo/1.0.0/demo-1.0.0.json"
        ]

    @patch('requests.sessions.Session.get')
    def test_artifactory_search_reports_search_method(self, session_get):
        session_get.return_value = self._gavc_response("1.0.0")
        provider = ArtifactoryProvider(registry_url="http://mock.artifactory/artifactory")

        result = provider.search_artifacts(
            Artifact(group_id="com.example", artifact_id="demo", version="1.0.0", extension="json"))

        assert result.method == "search"
        assert result.urls == ["https://search.example.com/1.0.0/demo-1.0.0.json"]

    @patch('requests.sessions.Session.head')
    @patch('requests.sessions.Session.get')
    def test_direct_miss_falls_back_to_search(self, session_get, session_head):
        session_head.return_value = self._head(status_code=404)
        session_get.return_value = self._gavc_response("1.0.0")
        finder = ArtifactFinder(artifact_provider=ArtifactoryProvider(
            registry_url="http://mock.artifactory/artifactory", repositories=["libs-release-local"]))

        urls = finder.find_artifact_urls(group_id="com.example", artifact_id="demo",
                                         version="1.0.0", extension="json")

        assert urls == ["https://search.example.com/1.0.0/demo-1.0.0.json"]

    @patch('requests.sessions.Session.head')
    @patch('requests.sessions.Session.get')
    def test_multiple_repositories_return_all_hits_in_order(self, session_get, session_head):
        session_head.return_value = self._head()
        finder = ArtifactFinder(artifact_provider=ArtifactoryProvider(
            registry_url="http://mock.artifactory/artifactory",
            repositories=["libs-release", "libs-staging", "libs-release"]))

        urls = finder.find_artifact_urls(group_id="com.example", artifact_id="demo",
                                         version="1.0.0", extension="json")

        assert urls == [
            "http://mock.artifactory/artifactory/libs-release/com/example/demo/1.0.0/demo-1.0.0.json",
            "http://mock.artifactory/artifactory/libs-staging/com/example/demo/1.0.0/demo-1.0.0.json",
        ]
        session_get.assert_not_called()

    @patch('requests.sessions.Session.head')
    @patch('requests.sessions.Session.get')
    def test_nexus_repository_suffix_falls_back_to_search_after_direct_miss(self, session_get, session_head):
        session_head.return_value = self._head(status_code=404)
        session_get.return_value = self._nexus_empty_search_response()
        finder = ArtifactFinder(artifact_provider=NexusProvider(
            registry_url="https://mock.nexus.url/repository", repositories=["maven-public"]))

        urls = finder.find_artifact_urls(group_id="com.example", artifact_id="demo",
                                         version="1.0.0", extension="json")

        assert urls == []
        session_head.assert_called_once_with(
            "https://mock.nexus.url/repository/maven-public/com/example/demo/1.0.0/demo-1.0.0.json",
            timeout=None, allow_redirects=True)

    @patch('requests.sessions.Session.head')
    @patch('requests.sessions.Session.get')
    def test_nexus_root_registry_falls_back_to_search_after_direct_miss(self, session_get, session_head):
        session_head.return_value = self._head(status_code=404)
        session_get.return_value = self._nexus_empty_search_response()
        finder = ArtifactFinder(artifact_provider=NexusProvider(
            registry_url="https://mock.nexus.url", repositories=["maven-public"]))

        urls = finder.find_artifact_urls(group_id="com.example", artifact_id="demo",
                                         version="1.0.0", extension="json")

        assert urls == []
        session_head.assert_called_once_with(
            "https://mock.nexus.url/repository/maven-public/com/example/demo/1.0.0/demo-1.0.0.json",
            timeout=None, allow_redirects=True)

    @patch('requests.sessions.Session.head')
    @patch('requests.sessions.Session.get')
    def test_nexus_browse_html_is_miss(self, session_get, session_head):
        session_head.side_effect = [
            self._head(status_code=404),
            self._head(headers={"Content-Type": "text/html; charset=UTF-8"}),
        ]
        session_get.return_value = self._nexus_empty_search_response()
        finder = ArtifactFinder(artifact_provider=NexusProvider(
            registry_url="https://mock.nexus.url/repository", repositories=["maven-public"]))

        urls = finder.find_artifact_urls(group_id="com.example", artifact_id="demo",
                                         version="1.0.0", extension="json")

        assert urls == []

    @patch('requests.sessions.Session.head')
    @patch('requests.sessions.Session.get')
    def test_artifactory_per_request_repositories_use_direct_resolution(self, session_get, session_head):
        session_head.return_value = self._head()
        provider = ArtifactoryProvider(registry_url="http://mock.artifactory/artifactory")

        result = provider.search_artifacts(
            Artifact(group_id="com.example", artifact_id="demo", version="1.0.0", extension="json"),
            repositories=["libs-release-local"])

        assert result.urls == [
            "http://mock.artifactory/artifactory/libs-release-local/com/example/demo/1.0.0/demo-1.0.0.json"
        ]
        session_get.assert_not_called()

    @patch('requests.sessions.Session.head')
    @patch('requests.sessions.Session.get')
    def test_nexus_per_request_repositories_use_direct_resolution(self, session_get, session_head):
        session_head.return_value = self._head()
        provider = NexusProvider(registry_url="https://mock.nexus.url")

        result = provider.search_artifacts(
            Artifact(group_id="com.example", artifact_id="demo", version="1.0.0", extension="json"),
            repositories=["maven-public"])

        assert result.urls == [
            "https://mock.nexus.url/repository/maven-public/com/example/demo/1.0.0/demo-1.0.0.json"
        ]
        session_get.assert_not_called()

    def test_invalid_repositories_config_raises(self):
        with pytest.raises(Exception):
            ArtifactoryProvider(registry_url="http://mock.artifactory/artifactory", repositories=[1])

    def test_factory_passes_repositories_to_providers(self):
        artifactory = ArtifactProviderFactory.create_artifactory_provider(
            {"registry_url": "http://mock.artifactory/artifactory", "repositories": ["libs-release"]}, {})
        nexus = ArtifactProviderFactory.create_nexus_provider(
            {"registry_url": "https://mock.nexus.url", "repositories": ["maven-public"]}, {})

        assert artifactory._content_bases[0].url == "http://mock.artifactory/artifactory/libs-release"
        assert nexus._content_bases[0].url == "https://mock.nexus.url/repository/maven-public"
