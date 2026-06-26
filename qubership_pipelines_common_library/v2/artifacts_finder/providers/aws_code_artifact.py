import logging
import boto3

from pathlib import Path
from botocore.config import Config
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact import Artifact
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact_provider import ArtifactProvider
from qubership_pipelines_common_library.v2.artifacts_finder.model.credentials import Credentials
from qubership_pipelines_common_library.v2.artifacts_finder.utils.artifact_finder_utils import ArtifactFinderUtils


class AwsCodeArtifactProvider(ArtifactProvider):

    def __init__(self, credentials: Credentials, domain: str, repository: str, package_format: str = "generic", **kwargs):
        """
        Initializes this client to work with **AWS Code Artifact** for generic or maven artifacts.
        Requires `Credentials` provided by `AwsCredentialsProvider`.

        This provider supports resolving `-SNAPSHOT` artifacts into latest version and searching for versions with asterisk-wildcards.
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

    def search_artifacts(self, artifact: Artifact, latest: bool = False, comparer=None, **kwargs) -> list[str]:
        namespaces = self._resolve_namespaces(artifact)
        if not namespaces:
            return []

        if artifact.has_version_wildcard():
            candidates = self._search_wildcard_versions(artifact, namespaces, latest=latest, comparer=comparer)
        else:
            candidates = []
            for namespace in namespaces:
                if artifact.is_snapshot():
                    resolved = self._resolve_snapshot_version(artifact, namespace)
                    if not resolved:
                        continue
                    logging.debug(f"Resolved SNAPSHOT version '{artifact.version}' -> '{resolved}' (namespace: {namespace})")
                    candidates.append((namespace, resolved))
                else:
                    candidates.append((namespace, artifact.version))

        results = []
        for namespace, package_version in candidates:
            results.extend(self._collect_assets(artifact, namespace, package_version))
        logging.info(f"AWS search results: {results}")
        return results

    def get_provider_name(self) -> str:
        return "aws_code_artifact"

    def _resolve_namespaces(self, artifact: Artifact) -> list[str]:
        if artifact.group_id:
            return [artifact.group_id]
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
        elif len(namespaces) > 1:
            logging.warning(f"Found multiple namespaces with same artifactId = {artifact.artifact_id}:\n{namespaces}")
        return namespaces

    def _search_wildcard_versions(self, artifact: Artifact, namespaces: list[str],
                                  latest: bool = False, comparer=None) -> list[tuple[str, str]]:
        # no server-side version wildcard support -> filter client-side
        version_pattern = ArtifactFinderUtils.wildcard_to_regex(artifact.version)
        candidates = [
            (namespace, ver)
            for namespace in namespaces
            for ver in self._list_all_package_versions(artifact, namespace)
            if version_pattern.fullmatch(ver)
        ]
        if latest:
            latest_pair = ArtifactFinderUtils.select_latest([(ver, (namespace, ver)) for namespace, ver in candidates], comparer)
            return [latest_pair] if latest_pair else []
        return candidates

    def _collect_assets(self, artifact: Artifact, namespace: str, package_version: str) -> list[str]:
        results = []
        try:
            assets_response = self._aws_client.list_package_version_assets(
                domain=self._domain, repository=self._repository,
                format=self._format, package=artifact.artifact_id,
                packageVersion=package_version, namespace=namespace
            )
            for asset in assets_response.get('assets'):
                if asset.get('name').lower().endswith(artifact.extension.lower()):
                    results.append(f"{assets_response.get('namespace')}/{assets_response.get('package')}/"
                                   f"{assets_response.get('version')}/{asset.get('name')}")
        except Exception:
            logging.warning(f"Specific version ({package_version}) of package ({namespace}.{artifact.artifact_id}) not found!")
        return results

    def _list_all_package_versions(self, artifact: Artifact, namespace: str) -> list[str]:
        versions = []
        next_token = None
        while True:
            kwargs = {
                'domain': self._domain,
                'repository': self._repository,
                'format': self._format,
                'package': artifact.artifact_id,
                'namespace': namespace,
            }
            if next_token:
                kwargs['nextToken'] = next_token

            response = self._aws_client.list_package_versions(**kwargs)
            versions.extend(entry.get('version', '') for entry in response.get('versions', []))

            next_token = response.get('nextToken')
            if not next_token:
                return versions

    def _resolve_snapshot_version(self, artifact: Artifact, namespace: str) -> str | None:
        candidate_versions = []
        for ver in self._list_all_package_versions(artifact, namespace):
            parsed = ArtifactFinderUtils.parse_snapshot_timestamp_version(ver)
            if parsed and f"{parsed[0]}-SNAPSHOT" == artifact.version:
                candidate_versions.append((parsed[1], ver))

        if not candidate_versions:
            logging.debug(f"No snapshot versions found for {artifact.artifact_id}:{artifact.version} in namespace '{namespace}'")
            return None

        candidate_versions.sort(key=lambda x: x[0], reverse=True)
        return candidate_versions[0][1]
