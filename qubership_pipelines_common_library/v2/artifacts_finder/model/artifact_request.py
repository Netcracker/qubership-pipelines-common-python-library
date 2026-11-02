from dataclasses import dataclass
from pathlib import Path

from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact import Artifact


@dataclass
class ArtifactRequest:
    artifact: Artifact
    repositories: str | list[str] | None = None
    download_path: str | Path | None = None
