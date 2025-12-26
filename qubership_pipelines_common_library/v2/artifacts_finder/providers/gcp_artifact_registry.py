from pathlib import Path
from google.cloud import artifactregistry_v1
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact import Artifact
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact_provider import ArtifactProvider
from qubership_pipelines_common_library.v2.artifacts_finder.model.credentials import Credentials


class GcpArtifactRegistryProvider(ArtifactProvider):

    def __init__(self, credentials: Credentials, project: str, region_name: str, repository: str, **kwargs):
        """
        Initializes this client to work with **GCP Artifact Registry** for generic artifacts.
        Requires `Credentials` provided by `GcpCredentialsProvider`.
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
        # works with both "Maven" and "Generic" type repositories
        name_filter = f"{self._repo_resource_id}/files/*{artifact.artifact_id}-{artifact.version}.{artifact.extension}"
        list_files_request = artifactregistry_v1.ListFilesRequest(
            parent=f"{self._repo_resource_id}",
            filter=f'name="{name_filter}"',
        )
        files = self._gcp_client.list_files(request=list_files_request)
        # logging.debug(f"[GCP search_artifacts] files: {files}")

        urls = []
        for file in files:
            download_url = f"https://artifactregistry.googleapis.com/download/v1/{file.name}:download?alt=media"
            urls.append(download_url)
        return urls

    def get_provider_name(self) -> str:
        return "gcp_artifact_registry"
