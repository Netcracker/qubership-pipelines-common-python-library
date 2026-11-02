import asyncio
import logging
from pathlib import Path

from qubership_pipelines_common_library.v2.artifacts_finder.bulk.bulk_downloader import BulkArtifactDownloader
from qubership_pipelines_common_library.v2.artifacts_finder.comparers.default_version_comparer import DefaultVersionComparer
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact import Artifact
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact_provider import ArtifactProvider
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact_request import ArtifactRequest
from qubership_pipelines_common_library.v2.artifacts_finder.model.bulk_download_report import BulkDownloadReport
from qubership_pipelines_common_library.v2.artifacts_finder.model.comparer import Comparer


class ArtifactFinder:
    """
    Allows searching for specific descriptor artifacts in different repositories without knowing full coordinates
    (e.g. knowing only `artifact_id` and `version`, but not its `group_id`)

    Supports different repository providers: Artifactory, Nexus, AWS, GCP, Azure. Initialize with one provider, or
    wrap an ordered list in a ``MultiArtifactProvider`` explicitly:

    ``finder = ArtifactFinder(artifact_provider=MultiArtifactProvider([ArtifactoryProvider(...), NexusProvider(...)]))``

    Providers might slightly differ in functionality, refer to the Provider docs

    Artifactory and Nexus providers accept an optional `repositories` list of repository keys. When it is set,
    searches with exact coordinates (a `group_id` and a version without wildcards) resolve download URLs directly
    against those repositories before falling back to the registry search API. This supports proxy, remote, and group
    repositories where search does not return uncached artifacts.

    A provider's `params` may set `max_retries` (default 0) to retry transient connection and server failures. A value
    of 0 disables retries, including the SDK defaults for AWS and GCP. When it is positive and `timeout` is unset, the
    provider uses a 30-second timeout. Requests-based providers retry GET and HEAD requests on 408, 429, 500, 502,
    503, and 504 and on connection and read errors; AWS and GCP use their SDK retry handling.

    Provides different auth methods for Cloud Providers, implementing `CloudCredentialsProvider` interface

    When searching with ``latest=True``, the newest version is chosen by a pluggable comparer.
    Pass a ``Comparer`` instance (e.g. ``SimpleVersionComparer()``); when omitted, a ``DefaultVersionComparer`` is used.

    Start by initializing this client with one of implementations:
    ``finder = ArtifactFinder(artifact_provider=ArtifactoryProvider(registry_url="https://our_url", username="user", password="password"))``

    Then find your artifacts using
    ``resource_urls = finder.find_artifact_urls(artifact_id='art_id', version='1.0.0', extension='json')``

    Additionally, perform filtering of returned results (if you expect to find more than one artifact), and then download necessary artifacts with
    ``finder.download_artifact(one_of_the_returned_resource_urls, './my_artifact.json')``

    To resolve and download several artifacts in parallel, use ``await finder.download_artifacts(...)`` or the
    synchronous ``finder.download_artifacts_sync(...)``. Both accept ``ArtifactRequest`` entries and return a
    ``BulkDownloadReport`` with one result per request. A request may set its own ``repositories`` and
    ``download_path``; the method-level ``repositories`` applies to requests that set none. ``repositories`` only
    affects the Artifactory and Nexus providers, where it enables direct URL resolution.

    For more complex providers (e.g. AWS Code Artifact), you need to use specific Credential Providers
    As an example:
    ```
    aws_creds = AwsCredentialsProvider().with_assume_role(...all the required params...).get_credentials()
    aws_code_artifact_provider = AwsCodeArtifactProvider(creds=creds, domain='our_domain', project='our_project')
    finder = ArtifactFinder(artifact_provider=aws_code_artifact_provider)
    ```
    """

    def __init__(self, artifact_provider: ArtifactProvider, comparer: Comparer = None, **kwargs):
        if not artifact_provider:
            raise Exception("Initialize ArtifactFinder with a registry artifact provider first!")
        self.provider = artifact_provider
        self.comparer = comparer if comparer is not None else DefaultVersionComparer()

    def find_artifact_urls(self, artifact_id: str = None, version: str = None, group_id: str = None,
                           extension: str = "jar", artifact: Artifact = None, latest: bool = False) -> list[str]:
        """
        :param version: Supports asterisk-wildcard (e.g. "main-*-RELEASE")
        :param latest: Will try to determine and return only the latest version among all versions found when searching for wildcard-containing version
        """
        if not artifact:
            artifact = Artifact(group_id=group_id, artifact_id=artifact_id, version=version, extension=extension)
        if not artifact.artifact_id or not artifact.version:
            raise Exception("Artifact 'artifact_id' and 'version' must be specified!")
        logging.debug(f"Searching for '{artifact.artifact_id}:{artifact.version}' in {self.provider.get_provider_name()}...")
        return self.provider.search_artifacts(artifact=artifact, latest=latest, comparer=self.comparer).urls

    def download_artifact(self, resource_url: str, local_path: str | Path, artifact: Artifact = None):
        from qubership_pipelines_common_library.v1.utils.utils_file import UtilsFile
        download_path = Path(local_path)
        if artifact:
            download_path = download_path.joinpath(artifact.get_filename())
        UtilsFile.create_parent_dirs(download_path)
        logging.debug(f"Downloading artifact from '{resource_url}' to '{download_path}'...")
        return self.provider.download_artifact(resource_url=resource_url, local_path=download_path)

    async def download_artifacts(self,
                                 artifacts: list[ArtifactRequest],
                                 download_dir: str | Path,
                                 repositories: str | list[str] = None,
                                 failfast: bool = False,
                                 max_workers: int = 8) -> BulkDownloadReport:
        """Resolve and download several artifacts, returning one result per request. The search resolves wildcard
        version to its newest match, a snapshot resolves to its latest build.

        ``repositories`` is the default for ArtifactRequests that set none; it only affects the Artifactory and Nexus
        providers, where it enables direct URL resolution. Files are saved into ``download_dir`` under the file name
        from the resolved URL, unless the request sets ``download_path``. If two requests resolve to the same target
        file, the first worker to claim it downloads and the other fails.

        With ``failfast=True``, the first artifact that is not found or fails stops new work; calls already running
        finish, the rest are marked skipped, the report is logged, and ``BulkArtifactDownloadError`` carrying the
        report is raised.
        """
        return await BulkArtifactDownloader(self, download_dir, repositories=repositories, failfast=failfast, max_workers=max_workers).run(artifacts)

    def download_artifacts_sync(self,
                                artifacts: list[ArtifactRequest],
                                download_dir: str | Path,
                                repositories: str | list[str] = None,
                                failfast: bool = False,
                                max_workers: int = 8) -> BulkDownloadReport:
        """Run ``download_artifacts`` and wait for its report."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.download_artifacts(artifacts=artifacts, download_dir=download_dir, repositories=repositories, failfast=failfast, max_workers=max_workers))
        raise RuntimeError("`download_artifacts_sync` cannot be called from a running event loop; `await download_artifacts` instead")
