import logging

import requests

from pathlib import Path
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact import Artifact
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact_provider import ArtifactProvider, ArtifactProviderError, ArtifactSearchResult
from qubership_pipelines_common_library.v2.artifacts_finder.utils.artifact_finder_utils import ArtifactFinderUtils
from qubership_pipelines_common_library.v2.artifacts_finder.utils.maven_direct_resolver import (
    MavenDirectResolutionMixin,
    RepositoryContentBase,
)


class ArtifactoryProvider(MavenDirectResolutionMixin, ArtifactProvider):

    def __init__(self, registry_url: str, username: str = None, password: str = None, repositories: str | list[str] = None, **kwargs):
        """
        Initializes this client to work with **JFrog Artifactory** maven repositories.
        Requires `username` and its `password` or `token`.

        Artifactory Artifact IDs are case-sensitive (`test-cli` and `test-CLI` are different artifacts)

        This provider supports resolving `-SNAPSHOT` artifacts into latest version and searching for versions with asterisk-wildcards.

        `repositories` is an ordered list of repository keys (a single key is also accepted). When it is set, requests
        with exact coordinates (a `group_id` and a version without wildcards) are resolved by constructing Maven-layout
        download URLs in those repositories and checking them, without calling the search API. This also works for
        proxy, remote, and virtual repositories that search does not index. The content base for a key is
        `{registry_url}/{key}`. If no constructed URL exists, the search API is used as a fallback.
        """
        super().__init__(**kwargs)
        self.registry_url = registry_url
        if password:
            from requests.auth import HTTPBasicAuth
            self._session.auth = HTTPBasicAuth(username, password)
        self._init_direct_resolution(repositories)

    def download_artifact(self, resource_url: str, local_path: str | Path, **kwargs) -> None:
        return self.generic_download(resource_url=resource_url, local_path=local_path)

    def search_artifacts(self, artifact: Artifact, latest: bool = False, comparer=None,
                         repositories: str | list[str] = None, **kwargs) -> ArtifactSearchResult:
        if artifact.has_version_wildcard():
            return ArtifactSearchResult(self._search_wildcard_versions(artifact, latest=latest, comparer=comparer), method="search")

        if direct_urls := self._resolve_direct_urls(artifact, repositories):
            return ArtifactSearchResult(direct_urls, method="direct")

        is_timestamped_snapshot = artifact.is_timestamped_snapshot()
        if is_timestamped_snapshot:
            base_version = f"{artifact.snapshot_base_version()}-SNAPSHOT"
        else:
            base_version = artifact.version

        search_params = {
            **({"g": artifact.group_id} if artifact.group_id else {}),
            "a": artifact.artifact_id,
            "v": base_version,
            "specific": "true"
        }
        results = self._gavc_search(search_params, artifact.artifact_id)
        download_urls = [
            result["downloadUri"] for result in results
            if result["ext"] == artifact.extension
            and (not is_timestamped_snapshot or result["downloadUri"].endswith(f"{artifact.version}.{artifact.extension}"))
        ]
        if artifact.is_snapshot():
            download_urls = ArtifactFinderUtils.resolve_snapshot_versions(artifact=artifact, download_urls=download_urls, provider=self)
        return ArtifactSearchResult(download_urls, method="search")

    def get_provider_name(self) -> str:
        return "artifactory"

    def _build_content_bases(self, keys: list[str]) -> list[RepositoryContentBase]:
        return [RepositoryContentBase(url=f"{self.registry_url.rstrip('/')}/{key}") for key in keys]

    def _search_wildcard_versions(self, artifact: Artifact, latest: bool = False, comparer=None) -> list[str]:
        search_params = {
            **({"g": artifact.group_id} if artifact.group_id else {}),
            "a": artifact.artifact_id,
            "v": artifact.version,
            "specific": "true"
        }
        results = self._gavc_search(search_params, artifact.artifact_id)
        # client-side pattern guard
        version_pattern = ArtifactFinderUtils.wildcard_to_regex(artifact.version)
        download_urls = [
            result["downloadUri"] for result in results
            if result["ext"] == artifact.extension and version_pattern.fullmatch(result["version"])
        ]
        if latest:
            latest_url = ArtifactFinderUtils.select_latest([(url.rsplit("/", 1)[-1], url) for url in download_urls], comparer)
            return [latest_url] if latest_url else []
        return download_urls

    def _gavc_search(self, search_params: dict, artifact_id: str) -> list[dict]:
        search_api_url = f"{self.registry_url}/api/search/gavc"
        logging.debug(f"Search URL: {search_api_url}"f"\nSearch Parameters: {search_params}")
        try:
            response = self.get_session().get(url=search_api_url, params=search_params, timeout=self.timeout)
        except requests.RequestException as e:
            raise Exception(f"Could not find '{artifact_id}' - {self._describe_request_error(e, 'GET', search_api_url, search_params)}") from e
        if response.status_code != 200:
            raise ArtifactProviderError(f"Could not find '{artifact_id}' - {self._describe_http_response(response, 'GET', search_api_url, search_params)}", status_code=response.status_code)
        return response.json().get("results", [])
