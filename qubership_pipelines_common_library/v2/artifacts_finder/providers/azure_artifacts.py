import logging
import re

from pathlib import Path
from requests.auth import HTTPBasicAuth
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact import Artifact
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact_provider import ArtifactProvider
from qubership_pipelines_common_library.v2.artifacts_finder.model.credentials import Credentials
from qubership_pipelines_common_library.v2.artifacts_finder.utils.artifact_finder_utils import ArtifactFinderUtils


class AzureArtifactsProvider(ArtifactProvider):

    def __init__(self, credentials: Credentials, organization: str, project: str, feed: str, **kwargs):
        """
        Initializes this client to work with **Azure Artifacts** for generic artifacts.
        Requires `Credentials` provided by `AzureCredentialsProvider`.

        This provider supports resolving `-SNAPSHOT` artifacts into latest version (in maven-format feeds)
        """
        super().__init__(**kwargs)
        self._credentials = credentials
        self._session.auth = HTTPBasicAuth("", self._credentials.access_token)
        self.organization = organization
        self.project = project
        self.feed = feed

    def download_artifact(self, resource_url: str, local_path: str | Path, **kwargs) -> None:
        return self.generic_download(resource_url=resource_url, local_path=local_path)

    def search_artifacts(self, artifact: Artifact, **kwargs) -> list[str]:
        acceptable_versions = [artifact.version]
        if timestamp_version_match := re.match(self.TIMESTAMP_VERSION_PATTERN, artifact.version):
            acceptable_versions.append(timestamp_version_match.group(1) + "SNAPSHOT")

        # Search all packages with matching artifact_id
        feeds_search_url = f"https://feeds.dev.azure.com/{self.organization}/{self.project}/_apis/packaging/feeds/{self.feed}/packages"
        name_query = f"{artifact.group_id}:{artifact.artifact_id}" if artifact.group_id else artifact.artifact_id
        feed_search_params = {
            "includeAllVersions": "false",
            "packageNameQuery": name_query,
            "protocolType": "maven",
            "api-version": "7.1",
        }
        feeds_response = self._session.get(url=feeds_search_url, params=feed_search_params, timeout=self.timeout)
        feeds_response_json = feeds_response.json()
        if feeds_response.status_code != 200:
            logging.error(f"Feeds search error ({feeds_response.status_code}) response: {feeds_response_json}")
            raise Exception(f"Could not find '{artifact.artifact_id}' - search request returned {feeds_response.status_code}!")

        logging.debug(f"Feeds search response: {feeds_response_json}")
        packages = feeds_response_json.get("value", [])
        if not packages:
            logging.warning("No packages were found.")
            return []
        if len(packages) > 1:
            logging.debug(f"Found multiple packages (groups) for '{artifact.artifact_id}', processing all")

        result_urls = []
        for feed_pkg in packages:
            pkg_links = feed_pkg.get("_links", {})
            pkg_versions_url = pkg_links.get("versions", {}).get("href", "")
            if not pkg_versions_url:
                continue

            pkg_versions_response = self._session.get(url=pkg_versions_url, params={"isDeleted": "false"}, timeout=self.timeout)
            if pkg_versions_response.status_code != 200:
                logging.warning(f"Skipping package, versions request returned {pkg_versions_response.status_code}")
                continue

            feed_versions = pkg_versions_response.json().get("value", [])
            if not feed_versions:
                continue

            # Filter by acceptable versions (stores snapshot versions literally: "5.0.0-SNAPSHOT")
            feed_version = [
                f for f in feed_versions
                if f.get("protocolMetadata", {}).get("data", {}).get("version") in acceptable_versions
            ]
            if not feed_version:
                continue
            filtered_feed_version = feed_version[0]
            feed_id = pkg_links.get("feed").get("href").split("/")[-1]
            feed_version = filtered_feed_version.get("version")
            group_id = filtered_feed_version.get("protocolMetadata", {}).get("data", {}).get("groupId")
            artifact_id = filtered_feed_version.get("protocolMetadata", {}).get("data", {}).get("artifactId")

            all_version_files = filtered_feed_version.get("files") or []
            if artifact.is_snapshot():
                base_version = artifact.version.removesuffix("-SNAPSHOT")
                candidate_files = []
                for f in all_version_files:
                    name = f.get("name", "")
                    if not name.startswith(f"{artifact.artifact_id}-") or not name.endswith(f".{artifact.extension}"):
                        continue
                    version_part = name.removeprefix(f"{artifact.artifact_id}-").removesuffix(f".{artifact.extension}")
                    parsed = ArtifactFinderUtils.parse_snapshot_timestamp_version(version_part)
                    if parsed and parsed[0] == base_version:
                        candidate_files.append((parsed[1], parsed[2], f))
                if not candidate_files:
                    logging.warning("No snapshot files found.")
                    continue
                candidate_files.sort(key=lambda x: (x[0], x[1]), reverse=True)
                target_file = candidate_files[0][2]
                logging.debug(f"Resolved SNAPSHOT version '{artifact.version}' -> '{target_file.get('name')}' (group_id: {group_id})")
            else:
                target_file = None
                for f in all_version_files:
                    name = f.get("name", "")
                    if name.startswith(f"{artifact.artifact_id}-") and name.endswith(f".{artifact.extension}"):
                        target_file = f
                        break
                if not target_file:
                    continue

            # Build download url
            target_file_name = target_file.get("name")

            download_url = (
                f"https://pkgs.dev.azure.com/{self.organization}/{self.project}/_apis/packaging/feeds/{feed_id}/maven/"
                f"{group_id}/{artifact_id}/{feed_version}/{target_file_name}/content"
                f"?api-version=7.1-preview.1"
            )
            result_urls.append(download_url)

        return result_urls

    def get_provider_name(self) -> str:
        return "azure_artifacts"
