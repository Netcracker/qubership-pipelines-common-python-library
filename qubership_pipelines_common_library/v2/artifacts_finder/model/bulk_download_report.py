from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact_request import ArtifactRequest


class BulkDownloadStatus(StrEnum):
    DOWNLOADED = "downloaded"
    NOT_FOUND = "not_found"
    FAILED = "failed"
    SKIPPED = "skipped"


class BulkDownloadReportStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class BulkDownloadResult:
    """Outcome of one bulk download request.

    `match_count` is the number of URLs the search returned, and `resolved_url` is the URL selected for download.
    `error` is None for a downloaded artifact and holds the reason otherwise.
    """

    request: ArtifactRequest
    status: BulkDownloadStatus
    match_count: int = 0
    resolved_url: str | None = None
    local_path: Path | None = None
    error: str | None = None
    search_duration: float | None = None
    download_duration: float | None = None
    total_duration: float | None = None
    resolution_method: str | None = None
    provider_name: str | None = None

    def __post_init__(self):
        self.status = BulkDownloadStatus(self.status)


@dataclass
class BulkDownloadReport:
    results: list[BulkDownloadResult]
    elapsed_seconds: float = 0.0

    @property
    def status(self) -> BulkDownloadReportStatus:
        if all(result.status == BulkDownloadStatus.DOWNLOADED for result in self.results):
            return BulkDownloadReportStatus.SUCCESS
        return BulkDownloadReportStatus.FAILED

    @property
    def search_duration(self) -> float:
        return sum(result.search_duration for result in self.results if result.search_duration is not None)

    @property
    def download_duration(self) -> float:
        return sum(result.download_duration for result in self.results if result.download_duration is not None)

    @property
    def requested_count(self) -> int:
        return len(self.results)

    @property
    def resolved_count(self) -> int:
        return sum(1 for result in self.results if result.resolved_url is not None)

    @property
    def downloaded_count(self) -> int:
        return sum(1 for result in self.results if result.status == BulkDownloadStatus.DOWNLOADED)

    @property
    def not_found_count(self) -> int:
        return sum(1 for result in self.results if result.status == BulkDownloadStatus.NOT_FOUND)

    @property
    def failed_count(self) -> int:
        return sum(1 for result in self.results if result.status == BulkDownloadStatus.FAILED)

    @property
    def skipped_count(self) -> int:
        return sum(1 for result in self.results if result.status == BulkDownloadStatus.SKIPPED)

    def to_dict(self) -> dict:
        """Return a JSON-serializable representation of this report."""
        return {
            "status": self.status.value,
            "elapsed_seconds": self.elapsed_seconds,
            "search_duration": self.search_duration,
            "download_duration": self.download_duration,
            "counts": {
                "requested": self.requested_count,
                "resolved": self.resolved_count,
                "downloaded": self.downloaded_count,
                "not_found": self.not_found_count,
                "failed": self.failed_count,
                "skipped": self.skipped_count,
            },
            "results": [
                {
                    "artifact": {
                        "group_id": result.request.artifact.group_id,
                        "artifact_id": result.request.artifact.artifact_id,
                        "version": result.request.artifact.version,
                        "extension": result.request.artifact.extension,
                    },
                    "repositories": result.request.repositories,
                    "download_path": str(result.request.download_path) if result.request.download_path else None,
                    "status": result.status.value,
                    "match_count": result.match_count,
                    "resolved_url": result.resolved_url,
                    "local_path": str(result.local_path) if result.local_path else None,
                    "error": result.error,
                    "search_duration": result.search_duration,
                    "download_duration": result.download_duration,
                    "total_duration": result.total_duration,
                    "resolution_method": result.resolution_method,
                    "provider_name": result.provider_name,
                }
                for result in self.results
            ],
        }


class BulkArtifactDownloadError(Exception):
    def __init__(self, message: str, report: BulkDownloadReport):
        super().__init__(message)
        self.report = report
