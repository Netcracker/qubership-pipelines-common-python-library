import os
import shutil
import tempfile
import zipfile
import requests

from pathlib import Path
from requests.auth import HTTPBasicAuth
from qubership_pipelines_common_library.v1.execution.exec_command import ExecutionCommand
from qubership_pipelines_common_library.v1.utils.utils_string import UtilsString


class DownloadArtifact(ExecutionCommand):
    """
    Downloads and unzips requested PYZ module to be used from Pipelines Declarative Executor (PDE)

    Supports `Artifact Finder` and `Direct Download` scenarios.

    If "systems.registry" section is present - command will initialize Artifact Finder and use it to either
    find and download artifact from registry (if "params.artifact_finder" data is specified with search params),
    or to get artifact via "params.artifact_url"

    Otherwise, during "Direct Download" command will use http session to get module from "params.artifact_url"
    (with optional authorization params from "systems.http" section)

    Input Parameters Structure (this structure is expected inside "input_params.params" block):
    ```
    {
        "target_path": "/app/sample_cli.pyz | /app/sample_cli",           # REQUIRED: Path where Artifact should be downloaded/extracted
        "artifact_url": "https://github.com/...your_release_asset.pyz",   # OPTIONAL: Direct URL where artifact is stored
        "artifact_finder": {                                              # OPTIONAL: Artifact Info to look up via ArtifactFinder,
            "artifact_id": "sample_cli_module",                                       `artifact_id` and `version` are required here,
            "group_id": "org.qubership",                                              `extension` defaults to "pyz" if not specified
            "version": "1.0.0",
            "extension": "pyz",
        },
        "timeout_seconds": 300,                                           # OPTIONAL: Maximum wait time for download in seconds for direct download
        "verify": true,                                                   # OPTIONAL: Sets up session's `verify` property (for both direct and artifact_finder flows)
        "clear_target_path": true,                                        # OPTIONAL: Whether download/extraction path should be cleared first
        "need_to_extract": true,                                          # OPTIONAL: Whether Artifact should be extracted to target_path (instead of just downloaded)
        "source_type": "AUTO"                                             # OPTIONAL: Specifies artifact download type (Git/FTP/S3 will be supported in further releases).
    }                                                                                 AUTO - derives type from other available params
    ```

    Systems Configuration (expected in "systems" block):
    ```
    {
        "http": {                                    # OPTIONAL: Auth settings for Direct-URL downloads
            "basic_auth": {                          # OPTIONAL: Sets up session with Basic Auth
                "username": "user",
                "password": "pass",
            },
            "headers_auth": {                       # OPTIONAL: Sets up session with provided headers
                "Authorization": "Bearer TOKEN",
            },
        },
        "registry": {                        # OPTIONAL: Auth settings for ArtifactFinder search/download,
            "artifactory": {                                    only section required for your provider should be present
                "registry_url": "artifactory_url",              Refer to ArtifactFinder docs and specific Cloud Providers for more information
                "username": "user",
                "password": "pass",
            },
            "nexus": {
                "registry_url": "nexus_url",
                "username": "user",
                "password": "pass",
            },
            "aws": {
                "auth_type": "DIRECT | ASSUME_ROLE",
                "domain": "test-maven-domain",
                "repository": "test-maven-repo",
                "package_format": "generic | maven",
                "access_key": "123",
                "secret_key": "456",
                "region_name": "456",
                "role_arn": "456", # For "OIDC_CREDS" auth_type
            },
            "gcp": {
                "auth_type": "SA_KEY | OIDC_CREDS",
                "project": "test-project",
                "region_name": "europe-west4",
                "repository": "test-repo",
                "service_account_key_path": "/user/keys/gcp_key.json", # Either path to key-file, or it's content as string
                "service_account_key_content": "123456",
                "oidc_credential_source": {}, # For "OIDC_CREDS" auth_type
                "audience": "aud", # For "OIDC_CREDS" auth_type
            },
            "azure": {
                "auth_type": "OAUTH2",
                "organization": "test_org",
                "project": "test_project",
                "feed": "test_feed",
                "tenant_id": "123",
                "client_id": "456",
                "client_secret": "789",
                "target_resource": "499b84ac-1321-427f-aa17-267ca6975798", # This specific UUID is the static resource ID for Azure DevOps
                "custom_auth_data": {},
            }
        }
    }
    ```

    Output Parameters:
        - params.target_path: Path where PYZ Module was extracted
        - params.file_size: File size of downloaded artifact (in bytes)
    """

    WAIT_TIMEOUT = 300

    def _validate(self):
        names = [
            "paths.input.params",
            "paths.output.params",
            "params.target_path",
        ]
        if not self.context.validate(names):
            return False

        self.artifact_url = self.context.input_param_get("params.artifact_url")
        self.artifact_info = self.context.input_param_get("params.artifact_finder", {})
        self.target_path = Path(self.context.input_param_get("params.target_path"))
        self.timeout_seconds = max(0, int(self.context.input_param_get("params.timeout_seconds", self.WAIT_TIMEOUT)))
        self.verify = UtilsString.convert_to_bool(self.context.input_param_get("params.verify", True))
        self.clear_target_path = UtilsString.convert_to_bool(self.context.input_param_get("params.clear_target_path", True))
        self.need_to_extract = UtilsString.convert_to_bool(self.context.input_param_get("params.need_to_extract", True))
        self.source_type = self.context.input_param_get("params.source_type", "AUTO")

        if self.context.input_param_get("systems.registry"):
            from qubership_pipelines_common_library.v2.artifacts_finder.utils.artifact_finder_utils import ArtifactFinderUtils
            self.artifact_finder = ArtifactFinderUtils.create_artifact_finder_for_command(self)
            if not self.artifact_url and not self.artifact_info:
                self.context.logger.error("Either 'artifact_url' or 'artifact_finder' info is required for Artifact Finder scenario")
                return False
        else:
            self.artifact_finder = None
            self.session = requests.Session()
            self.session.verify = self.verify
            if basic_auth := self.context.input_param_get("systems.http.basic_auth"):
                self.session.auth = HTTPBasicAuth(basic_auth.get("username"), basic_auth.get("password"))
            if headers_auth := self.context.input_param_get("systems.http.headers_auth"):
                self.session.headers.update(headers_auth)
            if not self.artifact_url:
                self.context.logger.error("'artifact_url' is mandatory for direct-download scenario")
                return False
        return True

    def _execute(self):
        self.context.logger.info("Running prepare-pyz-module...")
        self._prepare_target_path()
        downloaded_file_path = self._download_to_file()
        file_size = os.path.getsize(downloaded_file_path)
        self.context.logger.info(f"Downloaded to temporary file: {downloaded_file_path} ({file_size} bytes)")

        self._extract_to_path(downloaded_file_path, self.target_path)
        self.context.logger.info(f"{'Extracted' if self.need_to_extract else 'Moved'} to {self.target_path}")

        self.context.output_param_set("params.target_path", str(self.target_path))
        self.context.output_param_set("params.file_size", file_size)
        self.context.output_params_save()

    def _prepare_target_path(self):
        if self.clear_target_path and self.target_path.exists():
            if self.target_path.is_dir():
                shutil.rmtree(self.target_path)
            else:
                self.target_path.unlink()
        if self.need_to_extract:
            self.target_path.mkdir(parents=True, exist_ok=True)
        else:
            self.target_path.parent.mkdir(parents=True, exist_ok=True)

    def _download_to_file(self) -> str:
        try:
            if self.artifact_finder:
                if self.artifact_info:
                    self.context.logger.info("Searching for artifact using Artifact Finder...")
                    urls = self.artifact_finder.find_artifact_urls(
                        artifact_id=self.artifact_info.get("artifact_id"),
                        version=self.artifact_info.get("version"),
                        group_id=self.artifact_info.get("group_id"),
                        extension=self.artifact_info.get("extension", "pyz"),
                    )
                    if len(urls) < 1:
                        raise Exception(f"Could not find artifacts using provided parameters (artifact_info={self.artifact_info})")
                    resource_url = urls[0]
                else:
                    resource_url = self.artifact_url

                self.context.logger.info(f"Downloading using Artifact Finder from Resource URL: {resource_url}")
                with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_file:
                    tmp_path = tmp_file.name
                    self.artifact_finder.download_artifact(resource_url=resource_url, local_path=tmp_path)
                    return tmp_path

            else:
                self.context.logger.info(f"Downloading via HTTP from Direct URL: {self.artifact_url}")
                response = self.session.get(self.artifact_url, stream=True, timeout=self.timeout_seconds)
                response.raise_for_status()
                with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_file:
                    tmp_path = tmp_file.name
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            tmp_file.write(chunk)
                    return tmp_path

        except Exception as e:
            self._exit(False, f"Download failed: {e}")

    def _extract_to_path(self, source_path, target_path):
        try:
            if self.need_to_extract:
                with zipfile.ZipFile(source_path, 'r') as zip_ref:
                    zip_ref.extractall(target_path)
                os.unlink(source_path)
            else:
                shutil.move(str(source_path), str(target_path))
        except Exception as e:
            if os.path.exists(source_path):
                os.unlink(source_path)
            self._exit(False, f"Processing failed: {e}")
