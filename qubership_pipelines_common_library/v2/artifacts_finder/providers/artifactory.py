import logging
import re

from pathlib import Path
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact import Artifact
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact_provider import ArtifactProvider


class ArtifactoryProvider(ArtifactProvider):

    def __init__(self, registry_url: str, username: str = None, password: str = None, **kwargs):
        """
        Initializes this client to work with **JFrog Artifactory** maven repositories.
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
        timestamp_version_match = re.match(self.TIMESTAMP_VERSION_PATTERN, artifact.version)
        if timestamp_version_match:
            base_version = timestamp_version_match.group(1) + "SNAPSHOT"
        else:
            base_version = artifact.version

        search_params = {
            **({"g": artifact.group_id} if artifact.group_id else {}),
            "a": artifact.artifact_id,
            "v": base_version,
            "specific": "true"
        }
        search_api_url = f"{self.registry_url}/api/search/gavc"
        logging.debug(f"Search URL: {search_api_url}"f"\nSearch Parameters: {search_params}")

        response = self._session.get(url=search_api_url,
                                     params=search_params,
                                     timeout=self.timeout)
        if response.status_code != 200:
            raise Exception(f"Could not find '{artifact.artifact_id}' - search request returned {response.status_code}!")

        return [result["downloadUri"] for result in response.json()["results"]
                if result["ext"] == artifact.extension
                and (not timestamp_version_match or result["downloadUri"].endswith(f"{artifact.version}.{artifact.extension}"))]

    def get_provider_name(self) -> str:
        return "artifactory"
