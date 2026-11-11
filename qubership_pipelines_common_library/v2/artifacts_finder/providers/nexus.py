import requests

from pathlib import Path
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact import Artifact
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact_provider import ArtifactProvider, ArtifactProviderError, ArtifactSearchResult
from qubership_pipelines_common_library.v2.artifacts_finder.utils.artifact_finder_utils import ArtifactFinderUtils
from qubership_pipelines_common_library.v2.artifacts_finder.utils.maven_direct_resolver import (
    MavenDirectResolutionMixin,
    RepositoryContentBase,
)


class NexusProvider(MavenDirectResolutionMixin, ArtifactProvider):

    SEARCH_ASSETS_PATH = "/service/rest/v1/search/assets"
    TRAILING_WILDCARD_MIN_PREFIX = 3

    def __init__(self, registry_url: str, username: str = None, password: str = None, repositories: str | list[str] = None, **kwargs):
        """
        Initializes this client to work with **Sonatype Nexus Repository** for maven artifacts.
        Requires `username` and its `password` or `token`.

        Nexus Artifact IDs are case-sensitive (`test-cli` and `test-CLI` are different artifacts)

        This provider supports resolving `-SNAPSHOT` artifacts into latest version and searching for versions with asterisk-wildcards.

        `repositories` is an ordered list of repository names (a single name is also accepted). When it is set,
        requests with exact coordinates (a `group_id` and a version without wildcards) are resolved by constructing
        Maven-layout download URLs in those repositories and checking them, without calling the search API. This also
        works for proxy and group repositories that search does not index. The content base for a name is
        `{registry_url}/repository/{name}`; when `registry_url` already ends with `/repository`, the name is appended
        directly and the browse-view URL is used as a fallback. If no constructed URL exists, the search API is used
        as a fallback.
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

        search_params = self._base_search_params(artifact)
        if artifact.is_snapshot():
            search_params["maven.baseVersion"] = artifact.version
        else:
            search_params["version"] = artifact.version

        items = self._search_all_assets(search_params, artifact.artifact_id)
        download_urls = [item.get("downloadUrl") for item in items]
        if artifact.is_snapshot():
            download_urls = ArtifactFinderUtils.resolve_snapshot_versions(artifact=artifact, download_urls=download_urls, provider=self)
        return ArtifactSearchResult(download_urls, method="search")

    def get_provider_name(self) -> str:
        return "nexus"

    def _build_content_bases(self, keys: list[str]) -> list[RepositoryContentBase]:
        root = self.registry_url.rstrip("/")
        #host_root = root.removesuffix("/repository")
        content_root = root if root.endswith("/repository") else f"{root}/repository"
        # Legacy fallback for older Nexus instances where the normal content index is unavailable.
        #browse_root = f"{host_root}/service/rest/repository/browse"
        #return [RepositoryContentBase(url=f"{content_root}/{key}", fallback_url=f"{browse_root}/{key}") for key in keys]
        return [RepositoryContentBase(url=f"{content_root}/{key}") for key in keys]

    def _search_wildcard_versions(self, artifact: Artifact, latest: bool = False, comparer=None) -> list[str]:
        search_params = self._base_search_params(artifact)
        # Nexus only allows trailing wildcards server-side, and rejects one when the literal prefix is shorter
        # than 3 characters. The client-side pattern guard below is authoritative either way.
        prefix = artifact.version.split("*", 1)[0]
        if len(prefix) >= self.TRAILING_WILDCARD_MIN_PREFIX:
            search_params["version"] = f"{prefix}*"

        version_pattern = ArtifactFinderUtils.wildcard_to_regex(artifact.version)
        # pattern guard is matched against the version; latest is selected by filename;
        download_urls = [
            item["downloadUrl"]
            for item in self._search_all_assets(search_params, artifact.artifact_id)
            if version_pattern.fullmatch(item.get("maven2", {}).get("version", ""))
        ]
        if latest:
            latest_url = ArtifactFinderUtils.select_latest([(url.rsplit("/", 1)[-1], url) for url in download_urls], comparer)
            return [latest_url] if latest_url else []
        return download_urls

    def _search_all_assets(self, search_params: dict, artifact_id: str) -> list[dict]:
        items = []
        continuation_token = None
        while True:
            page_params = {**search_params, **({"continuationToken": continuation_token} if continuation_token else {})}
            search_url = f"{self.registry_url}{self.SEARCH_ASSETS_PATH}"
            try:
                response = self.get_session().get(url=search_url, params=page_params, timeout=self.timeout)
            except requests.RequestException as e:
                raise Exception(f"Could not find '{artifact_id}' - {self._describe_request_error(e, 'GET', search_url, page_params)}") from e
            if response.status_code != 200:
                raise ArtifactProviderError(f"Could not find '{artifact_id}' - {self._describe_http_response(response, 'GET', search_url, page_params)}", status_code=response.status_code)
            data = response.json()
            items.extend(data.get("items", []))
            continuation_token = data.get("continuationToken")
            if not continuation_token:
                return items

    @staticmethod
    def _base_search_params(artifact: Artifact) -> dict:
        return {
            "maven.extension": artifact.extension,
            "maven.artifactId": artifact.artifact_id,
            **({"maven.groupId": artifact.group_id} if artifact.group_id else {}),
        }
