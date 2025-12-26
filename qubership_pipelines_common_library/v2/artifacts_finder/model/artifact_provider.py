import requests

from pathlib import Path
from abc import ABC, abstractmethod
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact import Artifact


class ArtifactProvider(ABC):
    """Base class for all artifact providers"""

    TIMESTAMP_VERSION_PATTERN = "^(.*-)?([0-9]{8}\\.[0-9]{6}-[0-9]+)$"

    def __init__(self, params: dict = None, **kwargs):
        self.params = params if params else {}
        self._session = requests.Session()
        self._session.verify = self.params.get('verify', True)
        self.timeout = self.params.get('timeout', None)

    def generic_download(self, resource_url: str, local_path: str | Path):
        response = self._session.get(url=resource_url, timeout=self.timeout)
        response.raise_for_status()
        with open(local_path, 'wb') as file:
            file.write(response.content)

    @abstractmethod
    def download_artifact(self, resource_url: str, local_path: str | Path, **kwargs) -> None:
        pass

    @abstractmethod
    def search_artifacts(self, artifact: Artifact, **kwargs) -> list[str]:
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        pass
