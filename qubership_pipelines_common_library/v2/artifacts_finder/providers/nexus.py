from pathlib import Path
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact import Artifact
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact_provider import ArtifactProvider


class NexusProvider(ArtifactProvider):

    def __init__(self, registry_url: str, username: str = None, password: str = None, **kwargs):
        """
        Initializes this client to work with **Sonatype Nexus Repository** for maven artifacts.
        Requires `username` and its `password` or `token`.
        """
        super().__init__(**kwargs)
        self.registry_url = registry_url
        if password:
            from requests.auth import HTTPBasicAuth
            self._session.auth = HTTPBasicAuth(username, password)

    def download_artifact(self, resource_url: str, local_path: str | Path, **kwargs) -> None:
        return self.generic_download(resource_url=resource_url, local_path=local_path)

    def search_artifacts(self, artifact: Artifact, **kwargs) -> list[str]:
        search_params = {
            "maven.extension": artifact.extension,
            "maven.artifactId": artifact.artifact_id,
            **({"maven.groupId": artifact.group_id} if artifact.group_id else {}),
        }
        if artifact.is_snapshot():
            search_params["maven.baseVersion"] = artifact.version
        else:
            search_params["version"] = artifact.version

        response = self._session.get(url=f"{self.registry_url}/service/rest/v1/search/assets",
                                     params=search_params,
                                     timeout=self.timeout)
        if response.status_code != 200:
            raise Exception(f"Could not find '{artifact.artifact_id}' - search request returned {response.status_code}!")
        return [result["downloadUrl"] for result in response.json()["items"]]

    def get_provider_name(self) -> str:
        return "nexus"
