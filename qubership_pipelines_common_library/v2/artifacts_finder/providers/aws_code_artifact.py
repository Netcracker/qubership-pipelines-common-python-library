import logging
import boto3

from pathlib import Path
from botocore.config import Config
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact import Artifact
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact_provider import ArtifactProvider
from qubership_pipelines_common_library.v2.artifacts_finder.model.credentials import Credentials


class AwsCodeArtifactProvider(ArtifactProvider):

    def __init__(self, credentials: Credentials, domain: str, repository: str, package_format: str = "generic", **kwargs):
        """
        Initializes this client to work with **AWS Code Artifact** for generic or maven artifacts.
        Requires `Credentials` provided by `AwsCredentialsProvider`.
        """
        super().__init__(**kwargs)
        self._credentials = credentials
        self._domain = domain
        self._repository = repository
        self._format = package_format
        self._aws_client = boto3.client(
            service_name='codeartifact',
            config=Config(region_name=credentials.region_name),
            aws_access_key_id=credentials.access_key,
            aws_secret_access_key=credentials.secret_key,
            aws_session_token=credentials.session_token,
        )

    def download_artifact(self, resource_url: str, local_path: str | Path, **kwargs) -> None:
        """ 'resource_url' is actually AWS-specific resource_id, expected to be "namespace/package/version/asset_name" """
        asset_parts = resource_url.split("/")
        response = self._aws_client.get_package_version_asset(
            domain=self._domain, repository=self._repository,
            format=self._format, namespace=asset_parts[0],
            package=asset_parts[1], packageVersion=asset_parts[2],
            asset=asset_parts[3]
        )
        with open(local_path, 'wb') as file:
            file.write(response.get('asset').read())

    def search_artifacts(self, artifact: Artifact, **kwargs) -> list[str]:
        list_packages_response = self._aws_client.list_packages(
            domain=self._domain, repository=self._repository,
            format=self._format, packagePrefix=artifact.artifact_id
        )
        logging.debug(f"list_packages_response: {list_packages_response}")

        namespaces = [package.get('namespace') for package in list_packages_response.get('packages')
                      if package.get('package') == artifact.artifact_id]
        logging.debug(f"namespaces: {namespaces}")

        if not namespaces:
            logging.warning(f"Found no packages with artifactId = {artifact.artifact_id}!")
            return []
        if len(namespaces) > 1:
            logging.warning(f"Found multiple namespaces with same artifactId = {artifact.artifact_id}:\n{namespaces}")

        results = []
        for namespace in namespaces:
            try:
                assets_response = self._aws_client.list_package_version_assets(
                    domain=self._domain, repository=self._repository,
                    format=self._format, package=artifact.artifact_id,
                    packageVersion=artifact.version, namespace=namespace
                )
                logging.debug(f"assets: {assets_response}")
                for asset in assets_response.get('assets'):
                    if asset.get('name').lower().endswith(artifact.extension.lower()):
                        results.append(f"{assets_response.get('namespace')}/{assets_response.get('package')}/"
                                       f"{assets_response.get('version')}/{asset.get('name')}")
            except Exception:
                logging.warning(f"Specific version ({artifact.version}) of package ({namespace}.{artifact.artifact_id}) not found!")
        logging.info(f"AWS search results: {results}")
        return results

    def get_provider_name(self) -> str:
        return "aws_code_artifact"
