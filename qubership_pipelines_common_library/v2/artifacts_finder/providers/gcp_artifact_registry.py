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
    MAX_UPSTREAM_DEPTH = 5

    def __init__(self, credentials: Credentials, project: str, region_name: str, repository: str, **kwargs):
        """
        Initializes this client to work with **GCP Artifact Registry** for generic artifacts.
        Requires `Credentials` provided by `GcpCredentialsProvider`.

        This provider supports resolving `-SNAPSHOT` artifacts into latest version (in maven-format repositories)
        and searching for versions with asterisk-wildcards.

        Works with `standard`, `remote` and `virtual` repositories:

        - `standard` repositories are searched directly, and found artifacts are downloaded from them;
        - `remote` repositories only expose artifacts that were already cached by Artifact Registry;
        - `virtual` repositories are supported for the maven format only: they don't store artifacts themselves,
          so they are searched through their upstream repositories (recursively, in the order of the configured
          upstream priority), while found artifacts are downloaded from the `pkg.dev` endpoint of the virtual
          repository itself.

        Searching in a `virtual` repository requires read access to all the repositories included into it
        as upstreams (which is not needed for downloading artifacts from the virtual repository itself).
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
        self._repository_configs = {}
        self._repositories_to_search = None

    def download_artifact(self, resource_url: str, local_path: str | Path, **kwargs) -> None:
        response = self._authorized_session.get(url=resource_url, timeout=self.timeout)
        response.raise_for_status()
        with open(local_path, 'wb') as file:
            file.write(response.content)

    def search_artifacts(self, artifact: Artifact, latest: bool = False, comparer=None, **kwargs) -> list[str]:
        if artifact.has_version_wildcard():
            return self._search_wildcard_versions(artifact, latest=latest, comparer=comparer)
        if artifact.is_snapshot():
            return self._search_snapshot_artifacts(artifact)

        group_filter = self._group_filter(artifact)
        urls = []
        for parent_repo in self._search_repositories():
            name_filter = f"{parent_repo}/files/*{artifact.artifact_id}-{artifact.version}.{artifact.extension}"
            for file in self._list_files(parent_repo, name_filter):
                if group_filter and group_filter not in unquote(file.name):
                    continue
                urls.append(self._build_download_url(file.name, parent_repo))
        return ArtifactFinderUtils.deduplicate(urls)

    def get_provider_name(self) -> str:
        return "gcp_artifact_registry"

    def _search_wildcard_versions(self, artifact: Artifact, latest: bool = False, comparer=None) -> list[str]:
        literal = f"{artifact.artifact_id}-{artifact.version.split('*', 1)[0]}"

        version_pattern = ArtifactFinderUtils.wildcard_to_regex(artifact.version)
        group_filter = self._group_filter(artifact)
        name_prefix, name_suffix = f"{artifact.artifact_id}-", f".{artifact.extension}"
        candidates = []  # (version_string, download_url) pairs
        for parent_repo in self._search_repositories():
            for file in self._list_files(parent_repo, f"{parent_repo}/files/*{literal}*"):
                decoded = unquote(file.name)
                if group_filter and group_filter not in decoded:
                    continue
                filename = decoded.rsplit("/", 1)[-1].rsplit(":", 1)[-1]
                if not (filename.startswith(name_prefix) and filename.endswith(name_suffix)):
                    continue
                version = filename[len(name_prefix):-len(name_suffix)]
                if not version_pattern.fullmatch(version):
                    continue
                candidates.append((version, self._build_download_url(file.name, parent_repo)))

        candidates = ArtifactFinderUtils.deduplicate(candidates)
        if latest:
            latest_url = ArtifactFinderUtils.select_latest(candidates, comparer)
            return [latest_url] if latest_url else []
        return [url for _, url in candidates]

    def _list_files(self, parent_repo: str, name_filter: str):
        list_files_request = artifactregistry_v1.ListFilesRequest(
            parent=parent_repo,
            filter=f'name="{name_filter}"',
        )
        return self._gcp_client.list_files(request=list_files_request)

    def _search_repositories(self) -> list[str]:
        if self._repositories_to_search is None:
            if self._get_repository_mode() == artifactregistry_v1.Repository.Mode.VIRTUAL_REPOSITORY:
                self._repositories_to_search = self._collect_upstream_resource_ids()
            else:
                self._repositories_to_search = [self._repo_resource_id]
        return self._repositories_to_search

    def _collect_upstream_resource_ids(self) -> list[str]:
        # Upstreams are traversed in the order of descending priority, same as Artifact Registry does it
        upstream_ids, visited = [], set()

        def visit(resource_id: str, depth: int):
            if resource_id in visited or depth > self.MAX_UPSTREAM_DEPTH:
                return
            visited.add(resource_id)
            repository = self._get_repository(resource_id)
            if repository.mode == artifactregistry_v1.Repository.Mode.VIRTUAL_REPOSITORY:
                policies = sorted(repository.virtual_repository_config.upstream_policies,
                                  key=lambda policy: policy.priority, reverse=True)
                for policy in policies:
                    visit(policy.repository, depth + 1)
            else:
                upstream_ids.append(resource_id)

        visit(self._repo_resource_id, 0)
        return upstream_ids

    def _get_repository(self, resource_id: str):
        if resource_id not in self._repository_configs:
            self._repository_configs[resource_id] = self._gcp_client.get_repository(name=resource_id)
        return self._repository_configs[resource_id]

    def _get_repository_mode(self):
        return self._get_repository(self._repo_resource_id).mode

    def _build_download_url(self, file_name: str, parent_repo: str) -> str:
        if self._get_repository_mode() != artifactregistry_v1.Repository.Mode.VIRTUAL_REPOSITORY:
            return f"{self.GAR_URL_PREFIX}{file_name}{self.GAR_URL_SUFFIX}"
        if self._get_repository(self._repo_resource_id).format != artifactregistry_v1.Repository.Format.MAVEN:
            raise Exception(f"Repository '{self._repo_resource_id}' can't be served by a virtual repository: only maven repositories are supported")
        relative_path = unquote(file_name.removeprefix(f"{parent_repo}/files/"))
        return f"{self._pkg_dev_base_url()}/{relative_path}"

    def _search_snapshot_artifacts(self, artifact: Artifact) -> list[str]:
        prefix = "*"
        if artifact.group_id:
            prefix = f"*{artifact.group_id.replace('.', '/')}/"

        maven_base_url = self._pkg_dev_base_url()
        base_version = artifact.version.removesuffix("-SNAPSHOT")
        suffix = f"{artifact.artifact_id}/{artifact.version}/maven-metadata.xml"
        result_urls = []
        for parent_repo in self._search_repositories():
            for file in self._list_files(parent_repo, f"{parent_repo}/files/{prefix}{suffix}"):
                relative = unquote(file.name.removeprefix(f"{parent_repo}/files/"))
                if not relative.endswith(suffix):
                    continue
                group_path = relative.removesuffix(suffix).rstrip("/")
                if not group_path:
                    continue

                metadata_url = self._build_download_url(file.name, parent_repo)
                response = self._authorized_session.get(url=metadata_url, timeout=self.timeout)
                response.raise_for_status()
                timestamp = ArtifactFinderUtils.extract_metadata_snapshot_timestamp(response.content)
                resolved_version = f"{base_version}-{timestamp}"

                url = f"{maven_base_url}/{group_path}/{artifact.artifact_id}/{artifact.version}/{artifact.artifact_id}-{resolved_version}.{artifact.extension}"
                logging.debug(f"Resolved SNAPSHOT version '{artifact.version}' -> '{resolved_version}' (group: {group_path})")
                result_urls.append(url)

        return ArtifactFinderUtils.deduplicate(result_urls)

    def _pkg_dev_base_url(self) -> str:
        return f"https://{self._region_name}-maven.pkg.dev/{self._project}/{self._repository}"

    @staticmethod
    def _group_filter(artifact: Artifact) -> str | None:
        if artifact.group_id:
            return f"/{artifact.group_id.replace('.', '/')}/"
        return None
