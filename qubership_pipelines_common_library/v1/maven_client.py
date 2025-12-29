import json
import os
import pathlib
import re
import requests
import logging

from xml.etree import ElementTree
from requests.auth import HTTPBasicAuth


class Artifact:
    def __init__(self, artifact_id, version, extension='jar'):
        self.artifact_id = artifact_id
        self.version = version
        self.extension = "jar" if not extension else extension

    def is_snapshot(self):
        return self.version and self.version.endswith("SNAPSHOT")

    @staticmethod
    def from_string(artifact_str: str):
        parts = artifact_str.split(":")
        if len(parts) == 3:
            artifact, version = parts[1], parts[-1]
            return Artifact(artifact, version)


class MavenArtifactSearcher:
    """
    Allows searching for specific maven artifacts in different repositories without knowing full coordinates
    (e.g. knowing only `artifact_id` and `version`, but not its `group_id`)

    Supports different Maven repository providers: Artifactory, Nexus, AWS, GCP

    Start by initializing this client with one of implementations:
    ``maven_client = MavenArtifactSearcher(registry_url).with_artifactory(artifactory_user, artifactory_token)``

    Then find your artifacts using
    ``maven_client.find_artifact_urls('art_id', '1.0.0')``

    Additionally, perform filtering of returned results, and then download necessary artifacts with
    ``maven_client.download_artifact(one_of_the_returned_urls, './my_artifact.jar')``
    """

    TIMESTAMP_VERSION_PATTERN = "^(.*-)?([0-9]{8}\\.[0-9]{6}-[0-9]+)$"

    def __init__(self, registry_url: str, params: dict = None, **kwargs):
        self.is_init = False
        self._search_func = None
        self._download_func = None
        self.registry_url = registry_url.rstrip("/")
        self.params = params if params else {}
        self._session = requests.Session()
        self._session.verify = self.params.get('verify', True)
        self.timeout = self.params.get('timeout', None)

    def find_artifact_urls(self, artifact_id: str = None, version: str = None, extension: str = "jar",
                           artifact: Artifact = None) -> list[str]:
        """
        Finds and returns list of URLs (or resource IDs, for specific providers) to target artifacts.
        Client should be initialized with one of providers first.
        Doesn't require `group_id` to find artifacts.
        Works with either `artifact_id`/`version` or `Artifact` class as input parameters.
        """
        self._check_init()
        if not artifact:
            artifact = Artifact(artifact_id=artifact_id, version=version, extension=extension)
        if not artifact.artifact_id or not artifact.version:
            raise Exception("Artifact 'artifact_id' and 'version' must be specified!")
        logging.debug(f"Searching for '{artifact.artifact_id}' in {self.registry_url}...")
        return self._search_func(artifact=artifact)

    def download_artifact(self, url: str, local_path: str):
        """
        Downloads maven artifact from `url` to a `local_path` location
        (you need to provide full path, including filename, since we can't determine it from resource urls for some providers).
        `url` should be one of values returned by `find_artifact_urls`.
        Client should be initialized with one of providers first.
        """
        self._check_init()
        self._create_dir(local_path)
        logging.debug(f"Downloading artifact from '{url}' to '{local_path}'...")
        return self._download_func(url=url, local_path=local_path)

    def _check_init(self):
        if not self.is_init:
            raise Exception("Init client with one of registry implementations first, e.g. '.with_artifactory'!")

    def _create_dir(self, local_path: str):
        directory = os.path.dirname(local_path)
        if directory:
            pathlib.Path(directory).mkdir(parents=True, exist_ok=True)

    def _generic_download(self, url: str, local_path: str):
        response = self._session.get(url=url, timeout=self.timeout)
        response.raise_for_status()
        with open(local_path, 'wb') as file:
            file.write(response.content)

    def with_artifactory(self, username: str = None, password: str = None):
        """
        Initializes this client to work with **JFrog Artifactory** maven repositories.
        Requires `username` and its `password` or `token`.
        """
        if password:
            self._session.auth = HTTPBasicAuth(username, password)
        self._search_func = self._artifactory_search
        self._download_func = self._generic_download
        self.is_init = True
        return self

    def _artifactory_search(self, artifact: Artifact = None) -> list[str]:
        # 1.0, 1.1              - release
        # 1.0-SNAPSHOT          - snapshot head
        # 1.0-123456-2025125-1  - specific snapshot
        timestamp_version_match = re.match(self.TIMESTAMP_VERSION_PATTERN, artifact.version)
        if timestamp_version_match:
            base_version = timestamp_version_match.group(1) + "SNAPSHOT"
        else:
            base_version = artifact.version
        response = self._session.get(url=f"{self.registry_url}/api/search/gavc",
                                     params={"a": artifact.artifact_id, "v": base_version, "specific": "true"},
                                     timeout=self.timeout)
        if response.status_code != 200:
            raise Exception(f"Could not find '{artifact.artifact_id}' - search request returned {response.status_code}!")
        return [result["downloadUri"] for result in response.json()["results"]
                if result["ext"] == artifact.extension and (not timestamp_version_match or result["downloadUri"].endswith(f"{artifact.version}.{artifact.extension}"))]

    def with_nexus(self, username: str = None, password: str = None):
        """
        Initializes this client to work with **Sonatype Nexus Repository** for maven artifacts.
        Requires `username` and its `password` or `token`.
        """
        if password:
            self._session.auth = HTTPBasicAuth(username, password)
        self._search_func = self._nexus_search
        self._download_func = self._generic_download
        self.is_init = True
        return self

    def _nexus_search(self, artifact: Artifact = None) -> list[str]:
        search_params = {
            "maven.artifactId": artifact.artifact_id,
            "maven.extension": artifact.extension
        }
        if artifact.version.endswith("-SNAPSHOT"):
            search_params["maven.baseVersion"] = artifact.version
        else:
            search_params["version"] = artifact.version
        response = self._session.get(url=f"{self.registry_url}/service/rest/v1/search/assets",
                                     params=search_params,
                                     timeout=self.timeout)
        if response.status_code != 200:
            raise Exception(f"Could not find '{artifact.artifact_id}' - search request returned {response.status_code}!")
        return [result["downloadUrl"] for result in response.json()["items"]]

    def with_aws_code_artifact(self, access_key: str, secret_key: str, domain: str, region_name: str, repository: str):
        """
        Initializes this client to work with **AWS Code Artifact** repository.
        Requires `access_key` and `secret_key` of a service account.
        Also requires `domain`, `region_name` and `repository` of used AWS instance.
        """
        import boto3
        from botocore.config import Config
        self._aws_client = boto3.client(service_name='codeartifact',
                                        config=Config(region_name=region_name),
                                        aws_access_key_id=access_key,
                                        aws_secret_access_key=secret_key,
                                        )
        self._domain = domain
        self._repository = repository
        self._search_func = self._aws_search
        self._download_func = self._aws_download
        self.is_init = True
        return self

    def _aws_search(self, artifact: Artifact = None) -> list[str]:
        list_packages_response = self._aws_client.list_packages(domain=self._domain, repository=self._repository,
                                                 format="maven", packagePrefix=artifact.artifact_id)
        # namespace == group_id
        namespaces = [package.get('namespace') for package in list_packages_response.get('packages')
                      if package.get('package') == artifact.artifact_id]
        if not namespaces:
            logging.warning(f"Found no packages with artifactId = {artifact.artifact_id}!")
            return []
        if len(namespaces) > 1:
            logging.warning(f"Found multiple namespaces with same artifactId = {artifact.artifact_id}:\n{namespaces}")

        results = []
        for namespace in namespaces:
            try:
                resp = self._aws_client.list_package_version_assets(domain=self._domain, repository=self._repository,
                                                                       format="maven", package=artifact.artifact_id,
                                                                       packageVersion=artifact.version,
                                                                       namespace=namespace)
                for asset in resp.get('assets'):
                    if asset.get('name').lower().endswith(artifact.extension.lower()):
                        results.append(f"{resp.get('namespace')}/{resp.get('package')}/{resp.get('version')}/{asset.get('name')}")
            except Exception:
                logging.warning(f"Specific version ({artifact.version}) of package ({namespace}.{artifact.artifact_id}) not found!")
        return results

    def _aws_download(self, url: str, local_path: str):
        """`url` is actually AWS-specific `resource_id`, expected to be `namespace/package/version/asset_name`"""
        asset_parts = url.split("/")
        response = self._aws_client.get_package_version_asset(domain=self._domain, repository=self._repository,
                                                             format="maven", namespace=asset_parts[0],
                                                             package=asset_parts[1], packageVersion=asset_parts[2],
                                                             asset=asset_parts[3]
                                                             )
        with open(local_path, 'wb') as file:
            file.write(response.get('asset').read())

    def with_gcp_artifact_registry(self, credential_params: dict, project: str, region_name: str, repository: str):
        """
        Initializes this client to work with **Google Cloud Artifact Registry** repository.
        Supports different types of authorization in `credential_params` dict:
            - `service_account_key` key -> requires content of key-file (generate key-file for your service account first)
            - `oidc_token_path` and `audience` key -> path to text file ("/path/to/token/file.txt") with your OIDC token and your required audience.
        Audience should be "//iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/POOL_ID/providers/PROVIDER_ID"

        Also requires `project`, `region_name` and `repository` of used GCP instance.
        """
        from google.cloud import artifactregistry_v1
        from google.auth.transport.requests import AuthorizedSession
        self._gcp_scopes = ['https://www.googleapis.com/auth/cloud-platform']
        creds = self._gcp_get_credentials(credential_params)
        self._gcp_client = artifactregistry_v1.ArtifactRegistryClient(credentials=creds)
        self._session = AuthorizedSession(credentials=creds)

        self._gcp_download_url = f"https://{region_name}-maven.pkg.dev/{project}/{repository}"
        self._repo_resource_id = f"projects/{project}/locations/{region_name}/repositories/{repository}"
        self._search_func = self._gcp_search
        self._download_func = self._generic_download
        self.is_init = True
        return self

    def _gcp_get_credentials(self, credential_params: dict):
        if service_account_key := credential_params.get("service_account_key"):
            from google.oauth2 import service_account
            return service_account.Credentials.from_service_account_info(
                info=json.loads(service_account_key),
                scopes=self._gcp_scopes,
            )
        if credential_params.get("oidc_token_path") and credential_params.get("audience"):
            from google.auth import identity_pool
            return identity_pool.Credentials(
                audience=credential_params.get("audience"),
                subject_token_type="urn:ietf:params:oauth:token-type:jwt",
                credential_source={"file": credential_params.get("oidc_token_path")},
                scopes=self._gcp_scopes,
            )
        raise Exception("No valid authentication params found in credential_params!")

    def _gcp_search(self, artifact: Artifact = None) -> list[str]:
        timestamp_version_match = re.match(self.TIMESTAMP_VERSION_PATTERN, artifact.version)
        is_snapshot = artifact.version.endswith("-SNAPSHOT")
        if timestamp_version_match:
            base_version = timestamp_version_match.group(1) + "SNAPSHOT"
        else:
            base_version = artifact.version

        response_pager = self._gcp_client.list_maven_artifacts(parent=self._repo_resource_id)
        for gav in response_pager:
            if gav.artifact_id == artifact.artifact_id and gav.version == base_version:
                artifact_folder_url = "{gcp_download_url}/{group_path}/{artifact_id}/{version}".format(
                    gcp_download_url=self._gcp_download_url,
                    group_path=gav.group_id.replace('.', '/'),
                    artifact_id=gav.artifact_id,
                    version=gav.version
                )
                if is_snapshot:
                    latest_snapshot_version = self._find_latest_snapshot_version(artifact_folder_url, artifact.version)
                    return [f"{artifact_folder_url}/{gav.artifact_id}-{latest_snapshot_version}.{artifact.extension}"]
                else:
                    return [f"{artifact_folder_url}/{gav.artifact_id}-{artifact.version}.{artifact.extension}"]
        return []

    def _find_latest_snapshot_version(self, artifact_folder_url: str, snapshot_version: str) -> str:
        response = self._session.get(url=f"{artifact_folder_url}/maven-metadata.xml", timeout=self.timeout)
        response.raise_for_status()
        xml = ElementTree.fromstring(response.content)
        timestamp = xml.findall("./versioning/snapshot/timestamp")[0].text
        build_number = xml.findall("./versioning/snapshot/buildNumber")[0].text
        return snapshot_version.replace("SNAPSHOT", timestamp + "-" + build_number)
