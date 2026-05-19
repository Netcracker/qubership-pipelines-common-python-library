import logging

from pathlib import Path
from urllib.parse import unquote
from google.cloud import artifactregistry_v1
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact import Artifact
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact_provider import ArtifactProvider
from qubership_pipelines_common_library.v2.artifacts_finder.model.credentials import Credentials
from qubership_pipelines_common_library.v2.artifacts_finder.utils.artifact_finder_utils import ArtifactFinderUtils


class GcpArtifactRegistryProvider(ArtifactProvider):

    GAR_URL_PREFIX = "https://artifactregistry.googleapis.com/download/v1/"
    GAR_URL_SUFFIX = ":download?alt=media"

    def __init__(self, credentials: Credentials, project: str, region_name: str, repository: str, **kwargs):
        """
        Initializes this client to work with **GCP Artifact Registry** for generic artifacts.
        Requires `Credentials` provided by `GcpCredentialsProvider`.

        This provider supports resolving `-SNAPSHOT` artifacts into latest version (in maven-format repositories)
        """
        super().__init__(**kwargs)
        self._credentials = credentials
        self._project = project
        self._region_name = region_name
        self._repository = repository
        self._repo_resource_id = f"projects/{project}/locations/{region_name}/repositories/{repository}"

        self._gcp_client = artifactregistry_v1.ArtifactRegistryClient(
            credentials=self._credentials.google_credentials_object
        )
        self._authorized_session = self._credentials.authorized_session

    def download_artifact(self, resource_url: str, local_path: str | Path, **kwargs) -> None:
        response = self._authorized_session.get(url=resource_url, timeout=self.timeout)
        response.raise_for_status()
        with open(local_path, 'wb') as file:
            file.write(response.content)

    def search_artifacts(self, artifact: Artifact, **kwargs) -> list[str]:
        if artifact.is_snapshot():
            return self._search_snapshot_artifacts(artifact)

        name_filter = f"{self._repo_resource_id}/files/*{artifact.artifact_id}-{artifact.version}.{artifact.extension}"
        list_files_request = artifactregistry_v1.ListFilesRequest(
            parent=f"{self._repo_resource_id}",
            filter=f'name="{name_filter}"',
        )
        files = self._gcp_client.list_files(request=list_files_request)

        group_filter = None
        if artifact.group_id:
            group_filter = f"/{artifact.group_id.replace('.', '/')}/"
        urls = []
        for file in files:
            if group_filter and group_filter not in unquote(file.name):
                continue
            download_url = f"{self.GAR_URL_PREFIX}{file.name}{self.GAR_URL_SUFFIX}"
            urls.append(download_url)
        return urls

    def _search_snapshot_artifacts(self, artifact: Artifact) -> list[str]:
        prefix = "*"
        if artifact.group_id:
            prefix = f"*{artifact.group_id.replace('.', '/')}/"
        name_filter = f"{self._repo_resource_id}/files/{prefix}{artifact.artifact_id}/{artifact.version}/maven-metadata.xml"
        list_files_request = artifactregistry_v1.ListFilesRequest(
            parent=self._repo_resource_id,
            filter=f'name="{name_filter}"',
        )
        files = self._gcp_client.list_files(request=list_files_request)

        maven_base_url = f"https://{self._region_name}-maven.pkg.dev/{self._project}/{self._repository}"
        base_version = artifact.version.removesuffix("-SNAPSHOT")
        result_urls = []
        for file in files:
            relative = unquote(file.name.removeprefix(f"{self._repo_resource_id}/files/"))
            suffix = f"{artifact.artifact_id}/{artifact.version}/maven-metadata.xml"
            if not relative.endswith(suffix):
                continue
            group_path = relative.removesuffix(suffix).rstrip("/")
            if not group_path:
                continue

            metadata_url = f"{self.GAR_URL_PREFIX}{file.name}{self.GAR_URL_SUFFIX}"
            response = self._authorized_session.get(url=metadata_url, timeout=self.timeout)
            response.raise_for_status()
            timestamp = ArtifactFinderUtils.extract_metadata_snapshot_timestamp(response.content)
            resolved_version = f"{base_version}-{timestamp}"

            url = f"{maven_base_url}/{group_path}/{artifact.artifact_id}/{artifact.version}/{artifact.artifact_id}-{resolved_version}.{artifact.extension}"
            logging.debug(f"Resolved SNAPSHOT version '{artifact.version}' -> '{resolved_version}' (group: {group_path})")
            result_urls.append(url)

        return result_urls

    def get_provider_name(self) -> str:
        return "gcp_artifact_registry"
