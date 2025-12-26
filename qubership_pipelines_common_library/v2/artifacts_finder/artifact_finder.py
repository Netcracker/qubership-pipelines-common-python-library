import logging
from pathlib import Path

from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact import Artifact
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact_provider import ArtifactProvider


class ArtifactFinder:
    """
    Allows searching for specific descriptor artifacts in different repositories without knowing full coordinates
    (e.g. knowing only `artifact_id` and `version`, but not its `group_id`)

    Supports different repository providers: Artifactory, Nexus, AWS, GCP, Azure

    Provides different auth methods for Cloud Providers, implementing `CloudCredentialsProvider` interface

    Start by initializing this client with one of implementations:
    ``finder = ArtifactFinder(artifact_provider=ArtifactoryProvider(registry_url="https://our_url", username="user", password="password"))``

    Then find your artifacts using
    ``resource_urls = finder.find_artifact_urls(artifact_id='art_id', version='1.0.0', extension='json')``

    Additionally, perform filtering of returned results (if you expect to find more than one artifact), and then download necessary artifacts with
    ``finder.download_artifact(one_of_the_returned_resource_urls, './my_artifact.json')``

    For more complex providers (e.g. AWS Code Artifact), you need to use specific Credential Providers
    As an example:
    ```
    aws_creds = AwsCredentialsProvider().with_assume_role(...all the required params...).get_credentials()
    aws_code_artifact_provider = AwsCodeArtifactProvider(creds=creds, domain='our_domain', project='our_project')
    finder = ArtifactFinder(artifact_provider=aws_code_artifact_provider)
    ```
    """

    def __init__(self, artifact_provider: ArtifactProvider, **kwargs):
        if not artifact_provider:
            raise Exception("Initialize ArtifactFinder with one of registry artifact providers first!")
        self.provider = artifact_provider

    def find_artifact_urls(self, artifact_id: str = None, version: str = None, group_id: str = None,
                           extension: str = "jar", artifact: Artifact = None) -> list[str]:
        if not artifact:
            artifact = Artifact(group_id=group_id, artifact_id=artifact_id, version=version, extension=extension)
        if not artifact.artifact_id or not artifact.version:
            raise Exception("Artifact 'artifact_id' and 'version' must be specified!")
        logging.debug(f"Searching for '{artifact.artifact_id}:{artifact.version}' in {self.provider.get_provider_name()}...")
        return self.provider.search_artifacts(artifact=artifact)

    def download_artifact(self, resource_url: str, local_path: str | Path, artifact: Artifact = None):
        from qubership_pipelines_common_library.v1.utils.utils_file import UtilsFile
        download_path = Path(local_path)
        if artifact:
            download_path = download_path.joinpath(artifact.get_filename())
        UtilsFile.create_parent_dirs(download_path)
        logging.debug(f"Downloading artifact from '{resource_url}' to '{download_path}'...")
        return self.provider.download_artifact(resource_url=resource_url, local_path=download_path)
