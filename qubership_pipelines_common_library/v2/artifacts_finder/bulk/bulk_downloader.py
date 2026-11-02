import asyncio
import logging
import os
import threading
import time
import uuid

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact import Artifact
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact_provider import ArtifactProvider
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact_request import ArtifactRequest
from qubership_pipelines_common_library.v2.artifacts_finder.model.bulk_download_report import (
    BulkArtifactDownloadError,
    BulkDownloadReport,
    BulkDownloadReportStatus,
    BulkDownloadResult,
    BulkDownloadStatus,
)
from qubership_pipelines_common_library.v2.artifacts_finder.utils.maven_direct_resolver import normalize_repository_keys

SKIPPED_ERROR = "Skipped because an earlier artifact failed"
NOT_FOUND_ERROR = "No matching artifacts found"


@dataclass
class _RunState:
    claimed: dict[str, int] = field(default_factory=dict)
    claim_lock: threading.Lock = field(default_factory=threading.Lock)


@dataclass
class _Resolution:
    request: ArtifactRequest
    urls: list[str] = field(default_factory=list)
    error: str | None = None
    method: str = "search"
    provider: ArtifactProvider | None = None


class BulkArtifactDownloader:
    """Resolves and downloads each artifact in a worker, one request per worker.

    Each worker resolves its request and downloads the first match immediately, so resolution and download of
    different artifacts overlap. Providers are tried in the order configured on the finder; the winning provider
    downloads its own URL. If two requests resolve to the same target, the first worker to claim it downloads and the
    other fails. With failfast, the first failed or not-found result stops new submissions; in-flight workers finish,
    including their downloads, and the remaining requests are marked skipped.
    """

    def __init__(self, finder, download_dir: str | Path, repositories: str | list[str] = None,
                 failfast: bool = False, max_workers: int = 8):
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        self._finder = finder
        self._provider = finder.provider
        self._provider.configure_connection_pool(max_workers)
        self._download_dir = Path(download_dir)
        self._default_repositories = self._validate_repositories(repositories, "Bulk 'repositories'")
        self._failfast = failfast
        self._max_workers = max_workers

    async def run(self, artifacts: list[ArtifactRequest]) -> BulkDownloadReport:
        started = time.monotonic()
        requests = self._normalize_requests(artifacts)
        if not requests:
            return self._finish(self._report([], started))

        state = _RunState()
        pool = ThreadPoolExecutor(max_workers=self._max_workers, thread_name_prefix="artifact-bulk")
        try:
            results = await self._run_workers(
                pool, [(state, index, request) for index, request in enumerate(requests)],
                self._process, self._result_failed,
                lambda item, error: BulkDownloadResult(request=item[2], status=BulkDownloadStatus.FAILED, error=self._error_text(error))
            )
            self._mark_skipped(requests, results)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

        return self._finish(self._report(results, started))

    async def _run_workers(self, pool: ThreadPoolExecutor, items: list[tuple], worker, is_failure, on_error):
        """Run `worker` over `items` with a sliding window of at most `max_workers` calls.

        Returns one result per item (None for items never submitted after a failfast stop). An exception escaping a
        worker is converted through `on_error`.
        """
        loop = asyncio.get_running_loop()
        results = [None] * len(items)
        pending = {}
        next_index = 0
        aborted = False
        while next_index < len(items) or pending:
            while not aborted and next_index < len(items) and len(pending) < self._max_workers:
                future = loop.run_in_executor(pool, worker, *items[next_index])
                pending[future] = next_index
                next_index += 1
            if not pending:
                break
            done, _ = await asyncio.wait(set(pending), return_when=asyncio.FIRST_COMPLETED)
            for future in done:
                index = pending.pop(future)
                try:
                    results[index] = future.result()
                except Exception as e:
                    results[index] = on_error(items[index], e)
                if self._failfast and is_failure(results[index]):
                    aborted = True
        return results

    def _process(self, state: _RunState, index: int, request: ArtifactRequest) -> BulkDownloadResult:
        search_started = time.monotonic()
        resolution = self._resolve(request)
        search_duration = time.monotonic() - search_started
        provider = resolution.provider
        provider_name = provider.get_provider_name() if provider is not None else None

        if resolution.error is not None:
            return self._with_timing(BulkDownloadResult(request=request, status=BulkDownloadStatus.FAILED, error=resolution.error), search_duration, resolution.method)
        if not resolution.urls:
            return self._with_timing(BulkDownloadResult(request=request, status=BulkDownloadStatus.NOT_FOUND, error=NOT_FOUND_ERROR), search_duration, resolution.method)

        url = resolution.urls[0]
        match_count = len(resolution.urls)
        if match_count > 1:
            logging.warning("Artifact %s matched %s artifacts; selected %s", _describe_artifact(request.artifact), match_count, url)

        try:
            target = self._target_path(provider, request, url)
            key = os.path.normcase(os.path.abspath(str(target)))
            with state.claim_lock:
                owner = state.claimed.get(key)
                if owner is not None:
                    return self._with_timing(BulkDownloadResult(
                        request=request, status=BulkDownloadStatus.FAILED, match_count=match_count,
                        resolved_url=url, error=f"Target path '{target}' is already used by request #{owner + 1}",
                        provider_name=provider_name), search_duration, resolution.method)
                state.claimed[key] = index
        except Exception as e:
            return self._with_timing(BulkDownloadResult(
                request=request, status=BulkDownloadStatus.FAILED, match_count=match_count,
                resolved_url=url, error=self._error_text(e), provider_name=provider_name),
                search_duration, resolution.method)

        download_started = time.monotonic()
        result = self._download(provider, request, url, target, match_count)
        result.download_duration = time.monotonic() - download_started
        return self._with_timing(result, search_duration, resolution.method)

    @staticmethod
    def _with_timing(result: BulkDownloadResult, search_duration: float, method: str) -> BulkDownloadResult:
        result.search_duration = search_duration
        result.resolution_method = method
        result.total_duration = search_duration + (result.download_duration or 0.0)
        return result

    def _resolve(self, request: ArtifactRequest) -> _Resolution:
        try:
            repositories = request.repositories if request.repositories is not None else self._default_repositories
            search_kwargs = {
                "artifact": request.artifact,
                "latest": True,
                "comparer": self._finder.comparer,
            }
            if repositories is not None:
                search_kwargs["repositories"] = repositories
            search_result = self._provider.search_artifacts(**search_kwargs)
            provider = search_result.provider or self._provider
            return _Resolution(request=request, urls=list(search_result.urls),
                               method=search_result.method, provider=provider)
        except Exception as e:
            return _Resolution(request=request, error=self._error_text(e))

    def _download(self, provider: ArtifactProvider, request: ArtifactRequest, url: str, target: Path,
                  match_count: int) -> BulkDownloadResult:
        part_path = None
        provider_name = provider.get_provider_name()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            part_path = target.parent / f".download-{uuid.uuid4().hex}.part"
            provider.download_artifact(resource_url=url, local_path=part_path)
            os.replace(part_path, target)
        except Exception as e:
            if part_path is not None:
                try:
                    part_path.unlink(missing_ok=True)
                except OSError:
                    pass
            return BulkDownloadResult(request=request, status=BulkDownloadStatus.FAILED, match_count=match_count,
                                      resolved_url=url, error=self._error_text(e), provider_name=provider_name)
        return BulkDownloadResult(request=request, status=BulkDownloadStatus.DOWNLOADED, match_count=match_count,
                                  resolved_url=url, local_path=target, provider_name=provider_name)

    def _target_path(self, provider: ArtifactProvider, request: ArtifactRequest, url: str) -> Path:
        if request.download_path is not None:
            path = Path(request.download_path)
            target = path if path.is_absolute() else self._download_dir / path
        else:
            filename = provider.get_resource_filename(url)
            if not filename:
                raise ValueError(f"Could not derive a file name from '{url}'")
            target = self._download_dir / filename
        if not target.name:
            raise ValueError(f"Invalid target path '{target}'")
        return target

    def _normalize_requests(self, artifacts: list[ArtifactRequest]) -> list[ArtifactRequest]:
        requests = []
        for request in artifacts:
            if not isinstance(request, ArtifactRequest):
                raise TypeError("Bulk artifacts must be ArtifactRequest instances")
            if not request.artifact.artifact_id or not request.artifact.version:
                raise Exception("Artifact 'artifact_id' and 'version' must be specified!")
            self._validate_repositories(request.repositories, f"Artifact '{request.artifact.artifact_id}' repositories")
            requests.append(request)
        return requests

    @staticmethod
    def _validate_repositories(repositories: str | list[str] | None, label: str) -> list[str] | None:
        if repositories is None:
            return None
        keys = normalize_repository_keys(repositories)
        if not keys:
            raise Exception(f"{label} must contain at least one repository key")
        return keys

    @staticmethod
    def _result_failed(result: BulkDownloadResult) -> bool:
        return result.status != BulkDownloadStatus.DOWNLOADED

    def _mark_skipped(self, requests: list[ArtifactRequest], results: list):
        for index, result in enumerate(results):
            if result is None:
                results[index] = self._skipped_result(requests[index])

    @staticmethod
    def _skipped_result(request: ArtifactRequest) -> BulkDownloadResult:
        return BulkDownloadResult(request=request, status=BulkDownloadStatus.SKIPPED, error=SKIPPED_ERROR)

    @staticmethod
    def _error_text(error: Exception) -> str:
        return str(error) or type(error).__name__

    @staticmethod
    def _report(results: list, started: float) -> BulkDownloadReport:
        return BulkDownloadReport(results=results, elapsed_seconds=time.monotonic() - started)

    def _finish(self, report: BulkDownloadReport) -> BulkDownloadReport:
        self._log_report(report)
        if self._failfast and report.status == BulkDownloadReportStatus.FAILED:
            raise BulkArtifactDownloadError(f"Bulk artifact download stopped: {report.downloaded_count} of {report.requested_count} artifacts downloaded", report)
        return report

    @staticmethod
    def _log_report(report: BulkDownloadReport):
        lines = ["\n## Bulk Download Report ##"]
        sections = (
            ("downloaded", BulkDownloadStatus.DOWNLOADED,
             lambda result: f"  {_describe_artifact(result.request.artifact)} -> {result.local_path}{_format_timing(result)}"),
            ("not found", BulkDownloadStatus.NOT_FOUND,
             lambda result: f"  {_describe_artifact(result.request.artifact)}{_format_timing(result)}"),
            ("failed", BulkDownloadStatus.FAILED,
             lambda result: f"  {_describe_artifact(result.request.artifact)} -> {result.error}{_format_timing(result)}"),
            ("skipped", BulkDownloadStatus.SKIPPED,
             lambda result: f"  {_describe_artifact(result.request.artifact)}{_format_timing(result)}"),
        )
        for title, status, format_line in sections:
            group = [result for result in report.results if result.status == status]
            if group:
                lines.append(f"{title}:")
                lines.extend(format_line(result) for result in group)
        lines.append(
            f"\n{report.requested_count} requested, {report.resolved_count} resolved, "
            f"{report.downloaded_count} downloaded, {report.not_found_count} not found, "
            f"{report.failed_count} failed, {report.skipped_count} skipped in {report.elapsed_seconds:.2f}s")
        logging.info("\n".join(lines))


def _describe_artifact(artifact: Artifact) -> str:
    group = f"{artifact.group_id}:" if artifact.group_id else ""
    return f"{group}{artifact.artifact_id}:{artifact.version} ({artifact.extension})"


def _format_timing(result: BulkDownloadResult) -> str:
    parts = []
    if result.provider_name:
        parts.append(result.provider_name)
    if result.resolution_method:
        parts.append(result.resolution_method)
    if result.search_duration is not None:
        parts.append(f"{result.search_duration:.3f}s")
    if result.download_duration is not None:
        parts.append(f"{result.download_duration:.3f}s")
    return f" [{' | '.join(parts)}]" if parts else ""
