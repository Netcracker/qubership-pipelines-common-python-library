from pathlib import Path
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact import Artifact
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact_provider import ArtifactProvider
from qubership_pipelines_common_library.v2.artifacts_finder.utils.artifact_finder_utils import ArtifactFinderUtils


class NexusProvider(ArtifactProvider):

    SEARCH_ASSETS_PATH = "/service/rest/v1/search/assets"

    def __init__(self, registry_url: str, username: str = None, password: str = None, **kwargs):
        """
        Initializes this client to work with **Sonatype Nexus Repository** for maven artifacts.
        Requires `username` and its `password` or `token`.

        Nexus Artifact IDs are case-sensitive (`test-cli` and `test-CLI` are different artifacts)

        This provider supports resolving `-SNAPSHOT` artifacts into latest version and searching for versions with asterisk-wildcards.
        """
        super().__init__(**kwargs)
        self.registry_url = registry_url
        if password:
            from requests.auth import HTTPBasicAuth
            self._session.auth = HTTPBasicAuth(username, password)

    def download_artifact(self, resource_url: str, local_path: str | Path, **kwargs) -> None:
        return self.generic_download(resource_url=resource_url, local_path=local_path)

    def search_artifacts(self, artifact: Artifact, latest: bool = False, comparer=None, **kwargs) -> list[str]:
        if artifact.has_version_wildcard():
            return self._search_wildcard_versions(artifact, latest=latest, comparer=comparer)

        search_params = self._base_search_params(artifact)
        if artifact.is_snapshot():
            search_params["maven.baseVersion"] = artifact.version
        else:
            search_params["version"] = artifact.version

        items = self._search_all_assets(search_params, artifact.artifact_id)
        download_urls = [item.get("downloadUrl") for item in items]
        if artifact.is_snapshot():
            return ArtifactFinderUtils.resolve_snapshot_versions(artifact=artifact, download_urls=download_urls, provider=self)
        else:
            return download_urls

    def get_provider_name(self) -> str:
        return "nexus"

    def _search_wildcard_versions(self, artifact: Artifact, latest: bool = False, comparer=None) -> list[str]:
        search_params = self._base_search_params(artifact)
        # Nexus only allows trailing wildcards server-side
        prefix = artifact.version.split("*", 1)[0]
        if prefix:
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
            response = self._session.get(url=f"{self.registry_url}{self.SEARCH_ASSETS_PATH}",
                                         params=page_params,
                                         timeout=self.timeout)
            if response.status_code != 200:
                raise Exception(f"Could not find '{artifact_id}' - search request returned {response.status_code}!")
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
