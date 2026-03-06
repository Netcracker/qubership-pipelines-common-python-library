import os
import shutil
import tempfile
import zipfile
import requests

from pathlib import Path
from qubership_pipelines_common_library.v1.execution.exec_command import ExecutionCommand
from qubership_pipelines_common_library.v1.utils.utils_string import UtilsString


class PreparePyzModule(ExecutionCommand):
    """
    Downloads and unzips requested PYZ module to be used from Pipelines Declarative Executor (PDE)

    Input Parameters Structure (this structure is expected inside "input_params.params" block):
    ```
    {
        "download_url": "https://github.com/...your_release_asset.zip",   # REQUIRED: URL where PYZ Module is located
        "target_path": "/app/sample_cli",                                 # REQUIRED: Path where PYZ Module should be extracted
        "timeout_seconds": 1800,                                          # OPTIONAL: Maximum wait time for download in seconds
        "clear_target_path": true,                                        # OPTIONAL: Whether extraction path should be cleared first
    }
    ```

    Output Parameters:
        - params.target_path: Path where PYZ Module was extracted
    """

    WAIT_TIMEOUT = 1800

    def _validate(self):
        names = [
            "paths.input.params",
            "paths.output.params",
            "params.download_url",
            "params.target_path",
        ]
        if not self.context.validate(names):
            return False

        self.download_url = self.context.input_param_get("params.download_url")
        self.target_path = Path(self.context.input_param_get("params.target_path"))
        self.timeout_seconds = max(0, int(self.context.input_param_get("params.timeout_seconds", self.WAIT_TIMEOUT)))
        self.clear_target_path = UtilsString.convert_to_bool(self.context.input_param_get("params.clear_target_path", True))
        return True

    def _execute(self):
        # todo le: need tolerable input params structure for different auths;
        #       use different systems for different cloud providers?
        #       make it reusable in case we need same stuff in other commands?
        # todo le: need to think of an integration with ArtifactFinder; need flexible https auth;
        self.context.logger.info("Running prepare-pyz-module...")

        self._prepare_target_path()
        downloaded_file_path = self._download_to_file()
        file_size = os.path.getsize(downloaded_file_path)
        self.context.logger.info(f"Downloaded to temporary file: {downloaded_file_path} ({file_size} bytes)")

        self._extract_to_path(downloaded_file_path, self.target_path)
        self.context.logger.info(f"Extracted to {self.target_path}")

        self.context.output_param_set("params.target_path", str(self.target_path))
        self.context.output_param_set("params.file_size", file_size)
        self.context.output_params_save()

    def _prepare_target_path(self):
        if self.clear_target_path and self.target_path.exists() and self.target_path.is_dir():
            shutil.rmtree(self.target_path)
        self.target_path.mkdir(parents=True, exist_ok=True)

    def _download_to_file(self) -> str:
        self.context.logger.info(f"Downloading from {self.download_url}")
        try:
            response = requests.get(self.download_url, stream=True, timeout=self.timeout_seconds)
            response.raise_for_status()
        except Exception as e:
            self._exit(False, f"Download failed: {e}")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_file:
            tmp_path = tmp_file.name
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    tmp_file.write(chunk)
            return tmp_path

    def _extract_to_path(self, source_path, target_path):
        try:
            with zipfile.ZipFile(source_path, 'r') as zip_ref:
                zip_ref.extractall(target_path)
        except Exception as e:
            os.unlink(source_path)
            self._exit(False, f"Extraction failed: {e}")
        os.unlink(source_path)
