from unittest.mock import Mock

import pytest

from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact import Artifact
from qubership_pipelines_common_library.v2.artifacts_finder.utils.artifact_finder_utils import ArtifactFinderUtils
from qubership_pipelines_common_library.v2.artifacts_finder.utils.maven_direct_resolver import (
    MavenDirectResolver,
    RepositoryContentBase,
    normalize_repository_keys,
)

SNAPSHOT_METADATA = b"""<metadata><versioning><snapshotVersions>
    <snapshotVersion><classifier></classifier><extension>pom</extension><value>1.0.0-20240101.000000-2</value></snapshotVersion>
    <snapshotVersion><classifier>graph</classifier><extension>json</extension><value>1.0.0-20240101.000000-3</value></snapshotVersion>
    <snapshotVersion><classifier></classifier><extension>json</extension><value>1.0.0-20240101.000000-1</value></snapshotVersion>
</snapshotVersions></versioning></metadata>"""

TIMESTAMP_METADATA = (b"<metadata><versioning><snapshot><timestamp>20240101.000000</timestamp>"
                      b"<buildNumber>4</buildNumber></snapshot></versioning></metadata>")


def mock_response(status_code=200, content=b"", headers=None):
    response = Mock()
    response.status_code = status_code
    response.content = content
    response.headers = headers or {}
    response.close = Mock()
    return response


def artifact(version="1.0.0", extension="json", group_id="com.example"):
    return Artifact(group_id=group_id, artifact_id="demo", version=version, extension=extension)


class TestMavenDirectResolver:

    def test_direct_resolution_requires_group_and_exact_version(self):
        assert MavenDirectResolver.is_applicable(artifact())
        assert not MavenDirectResolver.is_applicable(artifact(group_id=None))
        assert not MavenDirectResolver.is_applicable(artifact(version="1.0.*"))

    def test_probe_follows_redirects(self):
        session = Mock()
        session.head.return_value = mock_response()
        resolver = MavenDirectResolver(session, timeout=5)

        urls = resolver.resolve(artifact(), [RepositoryContentBase("https://repo.example.com/releases")])

        assert urls == ["https://repo.example.com/releases/com/example/demo/1.0.0/demo-1.0.0.json"]
        session.head.assert_called_once_with(
            "https://repo.example.com/releases/com/example/demo/1.0.0/demo-1.0.0.json",
            timeout=5, allow_redirects=True,
        )

    def test_probe_falls_back_to_get_on_405(self):
        session = Mock()
        session.head.return_value = mock_response(status_code=405)
        get_response = mock_response()
        session.get.return_value = get_response
        resolver = MavenDirectResolver(session)

        urls = resolver.resolve(artifact(), [RepositoryContentBase("https://repo.example.com/releases")])

        assert urls == ["https://repo.example.com/releases/com/example/demo/1.0.0/demo-1.0.0.json"]
        session.get.assert_called_once_with(
            "https://repo.example.com/releases/com/example/demo/1.0.0/demo-1.0.0.json",
            timeout=None, allow_redirects=True, stream=True,
        )
        get_response.close.assert_called_once()

    def test_probe_auth_error_logged_and_continues(self, caplog):
        session = Mock()
        session.head.side_effect = [mock_response(status_code=403), mock_response(status_code=200)]
        resolver = MavenDirectResolver(session)

        with caplog.at_level("WARNING"):
            urls = resolver.resolve(artifact(), [
                RepositoryContentBase("https://repo.example.com/releases"),
                RepositoryContentBase("https://repo.example.com/snapshots"),
            ])

        assert urls == ["https://repo.example.com/snapshots/com/example/demo/1.0.0/demo-1.0.0.json"]
        assert "403" in caplog.text
        assert "https://repo.example.com/releases/com/example/demo/1.0.0/demo-1.0.0.json" in caplog.text

    def test_snapshot_metadata_prefers_matching_snapshot_version(self):
        session = Mock()
        session.get.return_value = mock_response(content=SNAPSHOT_METADATA)
        session.head.return_value = mock_response()
        resolver = MavenDirectResolver(session)

        urls = resolver.resolve(artifact(version="1.0.0-SNAPSHOT"),
                                [RepositoryContentBase("https://repo.example.com/snapshots")])

        assert urls == [
            "https://repo.example.com/snapshots/com/example/demo/1.0.0-SNAPSHOT/demo-1.0.0-20240101.000000-1.json"
        ]
        session.get.assert_called_once_with(
            "https://repo.example.com/snapshots/com/example/demo/1.0.0-SNAPSHOT/maven-metadata.xml",
            timeout=None, allow_redirects=True,
        )

    def test_snapshot_metadata_falls_back_to_timestamp(self):
        assert ArtifactFinderUtils.resolve_snapshot_version_from_metadata(
            TIMESTAMP_METADATA, "1.0.0", "json") == "1.0.0-20240101.000000-4"

    def test_snapshot_metadata_invalid_xml_returns_none(self):
        assert ArtifactFinderUtils.resolve_snapshot_version_from_metadata(b"<metadata>", "1.0.0", "json") is None

    def test_snapshot_metadata_404_is_not_a_warning(self, caplog):
        session = Mock()
        session.get.return_value = mock_response(status_code=404)
        session.head.return_value = mock_response(status_code=404)
        resolver = MavenDirectResolver(session)

        with caplog.at_level("WARNING"):
            urls = resolver.resolve(artifact(version="1.0.0-SNAPSHOT"),
                                    [RepositoryContentBase("https://repo.example.com/releases")])

        assert urls == []
        assert "Could not read snapshot metadata" not in caplog.text

    def test_snapshot_metadata_server_error_is_warned(self, caplog):
        session = Mock()
        session.get.return_value = mock_response(status_code=500)
        session.head.return_value = mock_response(status_code=404)
        resolver = MavenDirectResolver(session)

        with caplog.at_level("WARNING"):
            resolver.resolve(artifact(version="1.0.0-SNAPSHOT"),
                             [RepositoryContentBase("https://repo.example.com/releases")])

        assert "HTTP 500" in caplog.text

    def test_snapshot_request_candidate_order(self):
        session = Mock()
        session.get.return_value = mock_response(content=SNAPSHOT_METADATA)
        session.head.side_effect = [mock_response(status_code=404), mock_response(status_code=200)]
        resolver = MavenDirectResolver(session)

        urls = resolver.resolve(artifact(version="1.0.0-SNAPSHOT"),
                                [RepositoryContentBase("https://repo.example.com/snapshots")])

        assert urls == [
            "https://repo.example.com/snapshots/com/example/demo/1.0.0-SNAPSHOT/demo-1.0.0-SNAPSHOT.json"
        ]
        assert [call.args[0] for call in session.head.call_args_list] == [
            "https://repo.example.com/snapshots/com/example/demo/1.0.0-SNAPSHOT/demo-1.0.0-20240101.000000-1.json",
            "https://repo.example.com/snapshots/com/example/demo/1.0.0-SNAPSHOT/demo-1.0.0-SNAPSHOT.json",
        ]

    def test_timestamped_snapshot_candidate_order(self):
        session = Mock()
        session.head.side_effect = [mock_response(status_code=404), mock_response(status_code=200)]
        resolver = MavenDirectResolver(session)

        urls = resolver.resolve(artifact(version="1.0.0-20240101.000000-1"),
                                [RepositoryContentBase("https://repo.example.com/snapshots")])

        assert urls == [
            "https://repo.example.com/snapshots/com/example/demo/1.0.0-20240101.000000-1/"
            "demo-1.0.0-20240101.000000-1.json"
        ]
        assert [call.args[0] for call in session.head.call_args_list] == [
            "https://repo.example.com/snapshots/com/example/demo/1.0.0-SNAPSHOT/demo-1.0.0-20240101.000000-1.json",
            "https://repo.example.com/snapshots/com/example/demo/1.0.0-20240101.000000-1/"
            "demo-1.0.0-20240101.000000-1.json",
        ]
        session.get.assert_not_called()

    def test_multiple_repositories_return_all_hits_in_order(self):
        session = Mock()
        session.head.return_value = mock_response()
        resolver = MavenDirectResolver(session)

        urls = resolver.resolve(artifact(), [
            RepositoryContentBase("https://repo.example.com/a"),
            RepositoryContentBase("https://repo.example.com/b"),
            RepositoryContentBase("https://repo.example.com/a"),
        ])

        assert urls == [
            "https://repo.example.com/a/com/example/demo/1.0.0/demo-1.0.0.json",
            "https://repo.example.com/b/com/example/demo/1.0.0/demo-1.0.0.json",
        ]


class TestRepositoryKeys:

    def test_repository_keys_normalized_and_deduplicated(self):
        assert normalize_repository_keys(" libs-release/ ") == ["libs-release"]
        assert normalize_repository_keys([" /libs-release/ ", "libs-release", "libs-snapshot"]) == [
            "libs-release", "libs-snapshot"
        ]
        assert normalize_repository_keys(None) == []
        assert normalize_repository_keys([]) == []

    def test_invalid_repositories_config_raises(self):
        with pytest.raises(Exception):
            normalize_repository_keys([""])
        with pytest.raises(Exception):
            normalize_repository_keys(["/"])
        with pytest.raises(Exception):
            normalize_repository_keys([1])
        with pytest.raises(Exception):
            normalize_repository_keys(5)


class TestArtifactSnapshotClassification:

    def test_snapshot_base_version(self):
        assert artifact(version="1.0.0-SNAPSHOT").snapshot_base_version() == "1.0.0"
        assert artifact(version="1.0.0-20240101.120000-1").snapshot_base_version() == "1.0.0"
        assert artifact(version="1.0.0").snapshot_base_version() is None

    def test_parse_timestamped_version(self):
        assert Artifact.parse_timestamped_version("1.0.0-20240101.120000-1") == ("1.0.0", "20240101.120000-1", 1)
        assert Artifact.parse_timestamped_version("1.0.0-SNAPSHOT") is None
        assert Artifact.parse_timestamped_version(None) is None

    def test_timestamped_version_without_base_is_not_snapshot(self):
        art = artifact(version="20240101.120000-1")
        assert not art.is_timestamped_snapshot()
        assert art.snapshot_base_version() is None

    def test_is_snapshot_requires_hyphen_suffix(self):
        assert artifact(version="1.0.0-SNAPSHOT").is_snapshot()
        assert not artifact(version="1.0.0SNAPSHOT").is_snapshot()


class TestSearchSnapshotResolution:

    def test_search_snapshot_resolution_skips_unresolvable_candidate(self, caplog):
        provider = Mock()
        provider.timeout = None
        provider._session.get.return_value = mock_response(content=b"<metadata/>")

        with caplog.at_level("WARNING"):
            urls = ArtifactFinderUtils.resolve_snapshot_versions(
                artifact(version="1.0.0-SNAPSHOT"),
                ["https://repo.example.com/releases/com/example/demo/1.0.0-SNAPSHOT/demo-1.0.0-20240101.000000-1.json"],
                provider,
            )

        assert urls == []
        assert "Could not resolve snapshot version" in caplog.text
