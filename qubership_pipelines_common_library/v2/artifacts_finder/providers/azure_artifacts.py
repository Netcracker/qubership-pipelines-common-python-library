import logging
import re

from pathlib import Path
from requests.auth import HTTPBasicAuth
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact import Artifact
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact_provider import ArtifactProvider
from qubership_pipelines_common_library.v2.artifacts_finder.model.credentials import Credentials


class AzureArtifactsProvider(ArtifactProvider):

    def __init__(self, credentials: Credentials, organization: str, project: str, feed: str, **kwargs):
        """
        Initializes this client to work with **Azure Artifacts** for generic artifacts.
        Requires `Credentials` provided by `AzureCredentialsProvider`.
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

        # Try to find package with name ~ "artifact_id"
        feeds_search_url = f"https://feeds.dev.azure.com/{self.organization}/{self.project}/_apis/packaging/feeds/{self.feed}/packages"
        feed_search_params = {
            "includeAllVersions": "true",
            "packageNameQuery": artifact.artifact_id,
            "protocolType": "maven",
            "api-version": "7.1",
        }
        feeds_response = self._session.get(url=feeds_search_url, params=feed_search_params, timeout=self.timeout)
        feeds_response_json = feeds_response.json()
        if feeds_response.status_code != 200:
            logging.error(f"Feeds search error ({feeds_response.status_code}) response: {feeds_response_json}")
            raise Exception(f"Could not find '{artifact.artifact_id}' - search request returned {feeds_response.status_code}!")

        logging.debug(f"Feeds search response: {feeds_response_json}")
        if feeds_response_json.get("count") > 1:
            logging.warning("Found more than 1 feeds. Use the first one.")
        elif feeds_response_json.get("count") == 0:
            logging.warning("No feeds were found.")
            return []
        feed = feeds_response_json.get("value")[0]
        feed_links = feed.get("_links", {})

        # Get feed versions
        feed_versions_url = feed_links.get("versions", {}).get("href", "")
        feed_versions_response = self._session.get(url=feed_versions_url, timeout=self.timeout)
        feed_versions_response_json = feed_versions_response.json()
        if feed_versions_response.status_code != 200:
            logging.error(f"Feed versions error ({feed_versions_response.status_code}) response: {feed_versions_response_json}")
            raise Exception(f"Could not find feed versions, search request returned {feed_versions_response.status_code}!")
        logging.debug(f"Feed versions response: {feed_versions_response_json}")
        feed_versions = feed_versions_response_json.get("value")

        # Filter by acceptable versions
        logging.debug(f"Filtering by acceptable versions: '{acceptable_versions}'")
        feed_version = [f for f in feed_versions if (f.get('protocolMetadata').get('data').get('version') in acceptable_versions)]
        if len(feed_version) == 0:
            logging.warning("All feed versions filtered.")
            return []
        filtered_feed_version = feed_version[0]

        # Search for target file
        files = [f for f in filtered_feed_version.get("files") if f.get('name').startswith(f"{artifact.artifact_id}-{artifact.version}") and f.get('name').endswith(artifact.extension)]
        logging.debug(f"Files found: {files}")
        if len(files) == 0:
            logging.warning("All files filtered.")
            return []
        target_file = files[0]

        # Build download url
        feed_id = feed_links.get("feed").get("href").split("/")[-1] # take id from link to feed
        feed_version = filtered_feed_version.get("version")
        group_id = filtered_feed_version.get('protocolMetadata').get('data').get("groupId")
        artifact_id = filtered_feed_version.get('protocolMetadata').get('data').get("artifactId")
        target_file_name = target_file.get("name")

        download_url = (
            f"https://pkgs.dev.azure.com/{self.organization}/{self.project}/_apis/packaging/feeds/{feed_id}/maven/"
            f"{group_id}/{artifact_id}/{feed_version}/{target_file_name}/content"
            f"?api-version=7.1-preview.1"
        )
        logging.info(f"Azure search resulting url: {download_url}")
        return [download_url]

    def get_provider_name(self) -> str:
        return "azure_artifacts"
