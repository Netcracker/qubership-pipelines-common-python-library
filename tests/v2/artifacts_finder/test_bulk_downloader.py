import asyncio
import logging
import os
import threading
import time

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from google.api_core import exceptions as google_exceptions
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from qubership_pipelines_common_library.v2.artifacts_finder.artifact_finder import ArtifactFinder
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact import Artifact
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact_provider import (
    ArtifactProvider,
    ArtifactProviderError,
    ArtifactSearchResult,
)
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact_request import ArtifactRequest
from qubership_pipelines_common_library.v2.artifacts_finder.model.bulk_download_report import (
    BulkArtifactDownloadError,
    BulkDownloadReport,
    BulkDownloadReportStatus,
    BulkDownloadResult,
    BulkDownloadStatus,
)
from qubership_pipelines_common_library.v2.artifacts_finder.model.credentials import Credentials
from qubership_pipelines_common_library.v2.artifacts_finder.providers.aws_code_artifact import AwsCodeArtifactProvider
from qubership_pipelines_common_library.v2.artifacts_finder.providers.azure_artifacts import AzureArtifactsProvider
from qubership_pipelines_common_library.v2.artifacts_finder.providers.gcp_artifact_registry import (
    GcpArtifactRegistryProvider,
)
from qubership_pipelines_common_library.v2.artifacts_finder.providers.multi_artifact_provider import MultiArtifactProvider


class CustomAdapter(HTTPAdapter):
    pass


class FakeProvider(ArtifactProvider):

    def __init__(self, params=None, name="fake"):
        super().__init__(params=params)
        self.name = name
        self.results = {}
        self.download_errors = set()
        self.search_delay_for_all = 0.0
        self.search_delays = {}
        self.search_calls = []
        self.download_calls = []
        self._lock = threading.Lock()
        self.active = 0
        self.max_active = 0

    def search_artifacts(self, artifact: Artifact, latest: bool = False, comparer=None, **kwargs):
        with self._lock:
            self.search_calls.append({"artifact": artifact, "latest": latest, "kwargs": kwargs})
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            delay = self.search_delays.get(artifact.artifact_id, self.search_delay_for_all)
            if delay:
                time.sleep(delay)
            result = self.results.get((artifact.artifact_id, artifact.version), [])
            if isinstance(result, Exception):
                raise result
            return ArtifactSearchResult(urls=result or [])
        finally:
            with self._lock:
                self.active -= 1

    def download_artifact(self, resource_url: str, local_path: str | Path, **kwargs) -> None:
        self.download_calls.append((resource_url, Path(local_path)))
        Path(local_path).write_text(f"content of {resource_url}")
        if resource_url in self.download_errors:
            raise RuntimeError(f"download failed for {resource_url}")

    def get_provider_name(self) -> str:
        return self.name


def url_for(artifact: Artifact, version: str = None) -> str:
    version = version or artifact.version
    group = (artifact.group_id or "nogroup").replace(".", "/")
    return f"https://repo.example/{group}/{artifact.artifact_id}/{version}/{artifact.artifact_id}-{version}.{artifact.extension}"


def artifact(artifact_id: str = "demo", version: str = "1.0.0", extension: str = "json", group_id: str = "com.example"):
    return Artifact(group_id=group_id, artifact_id=artifact_id, version=version, extension=extension)


def finder_with(provider: FakeProvider) -> ArtifactFinder:
    return ArtifactFinder(artifact_provider=provider)


def finder_with_many(*providers: FakeProvider) -> ArtifactFinder:
    return ArtifactFinder(artifact_provider=MultiArtifactProvider(list(providers)))


def register(provider: FakeProvider, *artifacts: Artifact, urls: list[str] = None):
    for item in artifacts:
        provider.results[(item.artifact_id, item.version)] = urls if urls is not None else [url_for(item)]


class TestBulkDownload:

    def test_downloads_all_artifacts_and_reports_counts(self, tmp_path):
        provider = FakeProvider()
        one, two = artifact("one"), artifact("two", extension="yaml")
        register(provider, one, two)

        report = asyncio.run(finder_with(provider).download_artifacts(
            [ArtifactRequest(one), ArtifactRequest(two)], tmp_path, max_workers=2))

        assert report.status is BulkDownloadReportStatus.SUCCESS
        assert report.requested_count == 2
        assert report.resolved_count == 2
        assert report.downloaded_count == 2
        assert [result.local_path.name for result in report.results] == ["one-1.0.0.json", "two-1.0.0.yaml"]
        assert (tmp_path / "one-1.0.0.json").read_text() == f"content of {url_for(one)}"

    def test_report_to_dict_contains_counts_and_results(self, tmp_path):
        provider = FakeProvider()
        one = artifact("one")
        register(provider, one)

        report = asyncio.run(finder_with(provider).download_artifacts([ArtifactRequest(one)], tmp_path))

        data = report.to_dict()
        assert data["status"] == "success"
        assert data["counts"] == {"requested": 1, "resolved": 1, "downloaded": 1,
                                  "not_found": 0, "failed": 0, "skipped": 0}
        assert data["results"][0]["artifact"] == {
            "group_id": "com.example", "artifact_id": "one", "version": "1.0.0", "extension": "json"}
        assert data["results"][0]["resolved_url"] == url_for(one)
        assert data["search_duration"] >= 0
        assert data["download_duration"] >= 0
        result = data["results"][0]
        assert result["resolution_method"] == "search"
        assert result["search_duration"] >= 0
        assert result["download_duration"] >= 0
        assert result["total_duration"] == result["search_duration"] + result["download_duration"]

    def test_report_is_one_info_message_with_status_sections(self, tmp_path, caplog):
        provider = FakeProvider()
        one, missing, broken = artifact("one"), artifact("missing"), artifact("broken")
        provider.results[("broken", "1.0.0")] = RuntimeError("search exploded")
        register(provider, one)

        with caplog.at_level(logging.INFO):
            asyncio.run(finder_with(provider).download_artifacts(
                [ArtifactRequest(one), ArtifactRequest(missing), ArtifactRequest(broken)],
                tmp_path, max_workers=3))

        info_messages = [record.getMessage() for record in caplog.records if record.levelno == logging.INFO]
        assert len(info_messages) == 1
        message = info_messages[0]
        assert "downloaded:\n  com.example:one:1.0.0 (json) ->" in message
        assert " [search | " in message
        assert "\nnot found:\n  com.example:missing:1.0.0 (json) [search | " in message
        assert "\nfailed:\n  com.example:broken:1.0.0 (json) -> search exploded [search | " in message
        assert "skipped:" not in message
        assert message.splitlines()[-1].startswith(
            "3 requested, 1 resolved, 1 downloaded, 1 not found, 1 failed, 0 skipped in ")

    def test_not_found_and_search_failure_do_not_stop_other_artifacts(self, tmp_path):
        provider = FakeProvider()
        missing, broken, good = artifact("missing"), artifact("broken"), artifact("good")
        provider.results[("broken", "1.0.0")] = RuntimeError("search exploded")
        register(provider, good)

        report = asyncio.run(finder_with(provider).download_artifacts(
            [ArtifactRequest(missing), ArtifactRequest(broken), ArtifactRequest(good)],
            tmp_path, max_workers=3))

        assert report.status is BulkDownloadReportStatus.FAILED
        assert [result.status for result in report.results] == [
            BulkDownloadStatus.NOT_FOUND, BulkDownloadStatus.FAILED, BulkDownloadStatus.DOWNLOADED]
        assert report.results[1].error == "search exploded"
        assert report.not_found_count == 1
        assert report.failed_count == 1
        assert report.downloaded_count == 1
        not_found = report.results[0]
        assert not_found.search_duration is not None
        assert not_found.download_duration is None
        assert not_found.total_duration == not_found.search_duration
        assert not_found.resolution_method == "search"

    def test_download_failure_keeps_url_and_cleans_partial_file(self, tmp_path):
        provider = FakeProvider()
        one = artifact("one")
        register(provider, one)
        provider.download_errors.add(url_for(one))

        report = asyncio.run(finder_with(provider).download_artifacts([ArtifactRequest(one)], tmp_path))

        result = report.results[0]
        assert result.status is BulkDownloadStatus.FAILED
        assert result.resolved_url == url_for(one)
        assert result.local_path is None
        assert "download failed" in result.error
        assert not (tmp_path / "one-1.0.0.json").exists()
        assert list(tmp_path.glob("*.part")) == []

    def test_invalid_target_path_fails_only_that_request(self, tmp_path):
        provider = FakeProvider()
        good, bad = artifact("good"), artifact("bad")
        register(provider, good, bad)
        root_path = "C:\\" if os.name == "nt" else "/"

        report = asyncio.run(finder_with(provider).download_artifacts(
            [ArtifactRequest(good), ArtifactRequest(bad, download_path=root_path)], tmp_path, max_workers=2))

        assert report.downloaded_count == 1
        assert report.failed_count == 1
        assert report.results[1].status == BulkDownloadStatus.FAILED
        assert (tmp_path / "good-1.0.0.json").exists()

    def test_provider_iterable_error_becomes_failed_result(self, tmp_path):
        provider = FakeProvider()
        broken, good = artifact("broken"), artifact("good")
        register(provider, good)

        def failing_urls():
            raise RuntimeError("lazy urls exploded")
            yield  # pragma: no cover

        provider.results[("broken", "1.0.0")] = failing_urls()

        report = asyncio.run(finder_with(provider).download_artifacts(
            [ArtifactRequest(broken), ArtifactRequest(good)], tmp_path, max_workers=2))

        assert report.downloaded_count == 1
        assert report.results[0].status == BulkDownloadStatus.FAILED
        assert "lazy urls exploded" in report.results[0].error

    def test_multiple_matches_download_first_and_record_count(self, tmp_path):
        provider = FakeProvider()
        one = artifact("one")
        urls = [url_for(one), url_for(one, "1.0.1"), url_for(one, "1.0.2")]
        provider.results[("one", "1.0.0")] = urls

        report = asyncio.run(finder_with(provider).download_artifacts([ArtifactRequest(one)], tmp_path))

        assert report.results[0].status is BulkDownloadStatus.DOWNLOADED
        assert report.results[0].match_count == 3
        assert report.results[0].resolved_url == urls[0]
        assert provider.download_calls[0][0] == urls[0]

    def test_duplicate_resolved_targets_download_once(self, tmp_path):
        provider = FakeProvider()
        one = artifact("one")
        register(provider, one)

        report = asyncio.run(finder_with(provider).download_artifacts(
            [ArtifactRequest(one), ArtifactRequest(one)], tmp_path, max_workers=2))

        statuses = [result.status for result in report.results]
        assert statuses.count(BulkDownloadStatus.DOWNLOADED) == 1
        assert statuses.count(BulkDownloadStatus.FAILED) == 1
        failed = next(result for result in report.results if result.status == BulkDownloadStatus.FAILED)
        assert "already used by request #" in failed.error
        assert len(provider.download_calls) == 1

    def test_duplicate_explicit_download_paths_download_once(self, tmp_path):
        provider = FakeProvider()
        one, two = artifact("one"), artifact("two")
        register(provider, one, two)
        requests = [ArtifactRequest(one, download_path="shared.json"),
                    ArtifactRequest(two, download_path="shared.json")]

        report = asyncio.run(finder_with(provider).download_artifacts(requests, tmp_path, max_workers=2))

        statuses = [result.status for result in report.results]
        assert statuses.count(BulkDownloadStatus.DOWNLOADED) == 1
        assert statuses.count(BulkDownloadStatus.FAILED) == 1
        winner = statuses.index(BulkDownloadStatus.DOWNLOADED)
        loser = 1 - winner
        assert f"request #{winner + 1}" in report.results[loser].error
        expected_content = f"content of {url_for(one if winner == 0 else two)}"
        assert (tmp_path / "shared.json").read_text() == expected_content
        assert len(provider.download_calls) == 1

    def test_target_named_like_part_file_does_not_collide(self, tmp_path):
        provider = FakeProvider()
        one, two = artifact("one"), artifact("two")
        register(provider, one, two)
        requests = [ArtifactRequest(one, download_path="shared.bin"),
                    ArtifactRequest(two, download_path="shared.bin.part")]

        report = asyncio.run(finder_with(provider).download_artifacts(requests, tmp_path, max_workers=2))

        assert report.downloaded_count == 2
        assert (tmp_path / "shared.bin").read_text() == f"content of {url_for(one)}"
        assert (tmp_path / "shared.bin.part").read_text() == f"content of {url_for(two)}"

    def test_searches_always_use_latest(self, tmp_path):
        provider = FakeProvider()
        one = artifact("one")
        register(provider, one)

        asyncio.run(finder_with(provider).download_artifacts([ArtifactRequest(one)], tmp_path))

        assert provider.search_calls[0]["latest"] is True

    def test_repository_precedence_request_then_method(self, tmp_path):
        provider = FakeProvider()
        one, two, three = artifact("one"), artifact("two"), artifact("three")
        register(provider, one, two, three)
        requests = [ArtifactRequest(one, repositories=["request-repo"]), ArtifactRequest(two),
                    ArtifactRequest(three)]

        asyncio.run(finder_with(provider).download_artifacts(
            requests, tmp_path, repositories=["method-repo"], max_workers=3))

        calls = {call["artifact"].artifact_id: call for call in provider.search_calls}
        assert calls["one"]["kwargs"]["repositories"] == ["request-repo"]
        assert calls["two"]["kwargs"]["repositories"] == ["method-repo"]
        assert calls["three"]["kwargs"]["repositories"] == ["method-repo"]

    def test_no_repositories_kwarg_when_none_configured(self, tmp_path):
        provider = FakeProvider()
        one = artifact("one")
        register(provider, one)

        asyncio.run(finder_with(provider).download_artifacts([ArtifactRequest(one)], tmp_path))

        assert "repositories" not in provider.search_calls[0]["kwargs"]

    def test_report_keeps_input_order_when_completion_order_differs(self, tmp_path):
        provider = FakeProvider()
        slow, fast = artifact("slow"), artifact("fast")
        register(provider, slow, fast)
        provider.search_delays["slow"] = 0.1

        report = asyncio.run(finder_with(provider).download_artifacts(
            [ArtifactRequest(slow), ArtifactRequest(fast)], tmp_path, max_workers=2))

        assert [result.request.artifact.artifact_id for result in report.results] == ["slow", "fast"]

    def test_searches_run_in_parallel(self, tmp_path):
        provider = FakeProvider()
        provider.search_delay_for_all = 0.05
        artifacts = [artifact(f"demo{i}") for i in range(4)]
        register(provider, *artifacts)

        report = asyncio.run(finder_with(provider).download_artifacts(
            [ArtifactRequest(item) for item in artifacts], tmp_path, max_workers=4))

        assert report.downloaded_count == 4
        assert provider.max_active >= 2

    def test_cancellation_releases_the_event_loop(self, tmp_path):
        provider = FakeProvider()
        provider.search_delay_for_all = 1.0
        one = artifact("one")
        register(provider, one)

        started = time.monotonic()

        async def download_with_timeout():
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(
                    finder_with(provider).download_artifacts([ArtifactRequest(one)], tmp_path), timeout=0.1)

        asyncio.run(download_with_timeout())
        assert time.monotonic() - started < 0.6

    def test_empty_request_list_is_success(self, tmp_path):
        report = asyncio.run(finder_with(FakeProvider()).download_artifacts([], tmp_path))

        assert report.status is BulkDownloadReportStatus.SUCCESS
        assert report.requested_count == 0

    def test_invalid_entries_raise_before_any_search(self, tmp_path):
        provider = FakeProvider()
        finder = finder_with(provider)

        with pytest.raises(Exception, match="must be specified"):
            asyncio.run(finder.download_artifacts([ArtifactRequest(Artifact(artifact_id="demo"))], tmp_path))
        with pytest.raises(TypeError, match="ArtifactRequest"):
            asyncio.run(finder.download_artifacts([Artifact(artifact_id="demo", version="1.0.0")], tmp_path))
        with pytest.raises(TypeError, match="ArtifactRequest"):
            asyncio.run(finder.download_artifacts(["not-an-artifact"], tmp_path))

        assert provider.search_calls == []

    def test_invalid_repositories_raise_before_any_search(self, tmp_path):
        provider = FakeProvider()
        finder = finder_with(provider)

        with pytest.raises(Exception, match="repositories"):
            asyncio.run(finder.download_artifacts(
                [ArtifactRequest(artifact("one"), repositories=[1])], tmp_path))
        with pytest.raises(Exception, match="at least one repository key"):
            asyncio.run(finder.download_artifacts(
                [ArtifactRequest(artifact("one"), repositories=[])], tmp_path))
        with pytest.raises(Exception, match="at least one repository key"):
            asyncio.run(finder.download_artifacts(
                [ArtifactRequest(artifact("one"))], tmp_path, repositories=[]))

        assert provider.search_calls == []

    def test_invalid_max_workers_raises_before_any_search(self, tmp_path):
        provider = FakeProvider()
        with pytest.raises(ValueError, match="max_workers"):
            asyncio.run(finder_with(provider).download_artifacts(
                [ArtifactRequest(artifact("one"))], tmp_path, max_workers=0))
        assert provider.search_calls == []


class TestBulkFailfast:

    def test_stops_scheduling_after_first_failure(self, tmp_path):
        provider = FakeProvider()
        broken, good = artifact("broken"), artifact("good")
        provider.results[("broken", "1.0.0")] = RuntimeError("search exploded")
        register(provider, good)

        with pytest.raises(BulkArtifactDownloadError) as ex:
            asyncio.run(finder_with(provider).download_artifacts(
                [ArtifactRequest(broken), ArtifactRequest(good)], tmp_path, failfast=True, max_workers=1))

        report = ex.value.report
        assert [result.status for result in report.results] == [
            BulkDownloadStatus.FAILED, BulkDownloadStatus.SKIPPED]
        assert len(provider.search_calls) == 1
        assert report.status is BulkDownloadReportStatus.FAILED
        skipped = report.results[1]
        assert skipped.search_duration is None
        assert skipped.download_duration is None
        assert skipped.total_duration is None
        assert skipped.resolution_method is None

    def test_failfast_lets_in_flight_downloads_finish(self, tmp_path):
        provider = FakeProvider()
        broken, slow, untouched = artifact("broken"), artifact("slow"), artifact("untouched")
        provider.results[("broken", "1.0.0")] = RuntimeError("search exploded")
        register(provider, slow, untouched)
        provider.search_delays["slow"] = 0.1

        with pytest.raises(BulkArtifactDownloadError) as ex:
            asyncio.run(finder_with(provider).download_artifacts(
                [ArtifactRequest(broken), ArtifactRequest(slow), ArtifactRequest(untouched)],
                tmp_path, failfast=True, max_workers=2))

        report = ex.value.report
        assert [result.status for result in report.results] == [
            BulkDownloadStatus.FAILED, BulkDownloadStatus.DOWNLOADED, BulkDownloadStatus.SKIPPED]
        assert report.results[1].resolved_url == url_for(slow)
        assert report.resolved_count == 1
        assert {call["artifact"].artifact_id for call in provider.search_calls} == {"broken", "slow"}
        assert [url for url, _ in provider.download_calls] == [url_for(slow)]

    def test_not_found_also_triggers_failfast(self, tmp_path):
        provider = FakeProvider()
        missing, good = artifact("missing"), artifact("good")
        register(provider, good)

        with pytest.raises(BulkArtifactDownloadError):
            asyncio.run(finder_with(provider).download_artifacts(
                [ArtifactRequest(missing), ArtifactRequest(good)], tmp_path, failfast=True, max_workers=1))

    def test_download_failure_triggers_failfast(self, tmp_path):
        provider = FakeProvider()
        one, two = artifact("one"), artifact("two")
        register(provider, one, two)
        provider.download_errors.add(url_for(one))

        with pytest.raises(BulkArtifactDownloadError) as ex:
            asyncio.run(finder_with(provider).download_artifacts(
                [ArtifactRequest(one), ArtifactRequest(two)], tmp_path, failfast=True, max_workers=1))

        assert [result.status for result in ex.value.report.results] == [
            BulkDownloadStatus.FAILED, BulkDownloadStatus.SKIPPED]

    def test_failfast_report_includes_skipped_section(self, tmp_path, caplog):
        provider = FakeProvider()
        broken, good = artifact("broken"), artifact("good")
        provider.results[("broken", "1.0.0")] = RuntimeError("search exploded")
        register(provider, good)

        with caplog.at_level(logging.INFO):
            with pytest.raises(BulkArtifactDownloadError):
                asyncio.run(finder_with(provider).download_artifacts(
                    [ArtifactRequest(broken), ArtifactRequest(good)], tmp_path, failfast=True, max_workers=1))

        info_messages = [record.getMessage() for record in caplog.records if record.levelno == logging.INFO]
        assert len(info_messages) == 1
        message = info_messages[0]
        assert "failed:\n  com.example:broken:1.0.0 (json) -> search exploded [search | " in message
        assert "skipped:\n  com.example:good:1.0.0 (json)" in message
        assert "downloaded:" not in message
        assert not [record for record in caplog.records if record.levelno >= logging.WARNING]

    def test_failfast_raises_after_duplicate_target_is_claimed(self, tmp_path):
        provider = FakeProvider()
        one, two = artifact("one"), artifact("two")
        register(provider, one, two)
        requests_list = [ArtifactRequest(one, download_path="shared.json"),
                         ArtifactRequest(two, download_path="shared.json")]

        with pytest.raises(BulkArtifactDownloadError) as ex:
            asyncio.run(finder_with(provider).download_artifacts(
                requests_list, tmp_path, failfast=True, max_workers=2))

        report = ex.value.report
        statuses = [result.status for result in report.results]
        assert statuses.count(BulkDownloadStatus.DOWNLOADED) == 1
        assert statuses.count(BulkDownloadStatus.FAILED) == 1
        assert len(provider.download_calls) == 1
        failed = next(result for result in report.results if result.status == BulkDownloadStatus.FAILED)
        assert "already used by request #" in failed.error


class TestMultipleProvidersBulk:

    def test_resolution_falls_through_and_report_names_provider(self, tmp_path):
        first, second = FakeProvider(name="first"), FakeProvider(name="second")
        one = artifact("one")
        register(second, one)

        report = asyncio.run(finder_with_many(first, second).download_artifacts(
            [ArtifactRequest(one)], tmp_path))

        assert report.downloaded_count == 1
        assert report.results[0].provider_name == "second"
        assert report.to_dict()["results"][0]["provider_name"] == "second"
        assert (tmp_path / "one-1.0.0.json").exists()

    def test_provider_error_falls_through_to_next_provider(self, tmp_path):
        first, second = FakeProvider(name="first"), FakeProvider(name="second")
        one = artifact("one")
        first.results[("one", "1.0.0")] = RuntimeError("first exploded")
        register(second, one)

        report = asyncio.run(finder_with_many(first, second).download_artifacts(
            [ArtifactRequest(one)], tmp_path))

        assert report.downloaded_count == 1
        assert report.results[0].provider_name == "second"

    @pytest.mark.parametrize("status_code", [401, 403, 429])
    def test_unavailable_provider_is_skipped_for_remaining_artifacts(self, tmp_path, status_code):
        first, second = FakeProvider(name="first"), FakeProvider(name="second")
        one, two = artifact("one"), artifact("two")
        first.results[("one", "1.0.0")] = ArtifactProviderError("provider rejected request", status_code=status_code)
        register(second, one, two)

        report = asyncio.run(finder_with_many(first, second).download_artifacts(
            [ArtifactRequest(one), ArtifactRequest(two)], tmp_path, max_workers=1))

        assert report.downloaded_count == 2
        assert [result.provider_name for result in report.results] == ["second", "second"]
        assert len(first.search_calls) == 1

    def test_only_provider_failure_fails_remaining_artifacts_without_network(self, tmp_path):
        provider = FakeProvider(name="only")
        one, two = artifact("one"), artifact("two")
        provider.results[("one", "1.0.0")] = ArtifactProviderError("provider rejected request", status_code=401)
        register(provider, two)

        report = asyncio.run(finder_with(provider).download_artifacts(
            [ArtifactRequest(one), ArtifactRequest(two)], tmp_path, max_workers=1))

        assert report.failed_count == 2
        assert len(provider.search_calls) == 1
        assert "Provider 'only' unavailable: authentication failed (HTTP 401)" in report.results[1].error

    def test_all_provider_errors_fail_with_aggregate_message(self, tmp_path):
        first, second = FakeProvider(name="first"), FakeProvider(name="second")
        one = artifact("one")
        first.results[("one", "1.0.0")] = RuntimeError("first exploded")
        second.results[("one", "1.0.0")] = RuntimeError("second exploded")

        report = asyncio.run(finder_with_many(first, second).download_artifacts(
            [ArtifactRequest(one)], tmp_path))

        assert report.failed_count == 1
        error = report.results[0].error
        assert "- first: first exploded" in error
        assert "- second: second exploded" in error

    def test_log_bracket_starts_with_winning_provider(self, tmp_path, caplog):
        first, second = FakeProvider(name="first"), FakeProvider(name="second")
        one = artifact("one")
        register(second, one)

        with caplog.at_level(logging.INFO):
            asyncio.run(finder_with_many(first, second).download_artifacts(
                [ArtifactRequest(one)], tmp_path))

        message = next(record.getMessage() for record in caplog.records if record.levelno == logging.INFO)
        assert "[second | search | " in message


class TestBulkSyncWrapper:

    def test_sync_wrapper_returns_report(self, tmp_path):
        provider = FakeProvider()
        one = artifact("one")
        register(provider, one)

        report = finder_with(provider).download_artifacts_sync([ArtifactRequest(one)], tmp_path)

        assert report.status is BulkDownloadReportStatus.SUCCESS
        assert (tmp_path / "one-1.0.0.json").exists()

    def test_sync_wrapper_refuses_to_run_inside_event_loop(self, tmp_path):
        finder = finder_with(FakeProvider())

        async def call_sync_wrapper():
            with pytest.raises(RuntimeError, match="running event loop"):
                finder.download_artifacts_sync([ArtifactRequest(artifact("one"))], tmp_path)

        asyncio.run(call_sync_wrapper())


class TestProviderSessionsAndFilenames:

    def test_thread_local_sessions_differ_and_copy_settings(self):
        provider = FakeProvider()
        provider._session.auth = ("user", "password")
        provider._session.verify = False
        provider._session.cookies.set("session", "cookie-value")
        provider._session.params["key"] = "value"
        provider._session.max_redirects = 5
        provider._session.headers["X-Test"] = "header-value"
        sessions = {}

        def capture(name):
            sessions[name] = provider.get_session()

        threads = [threading.Thread(target=capture, args=(name,)) for name in ("first", "second")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert sessions["first"] is not sessions["second"]
        assert sessions["first"] is not provider._session
        assert sessions["first"].auth == ("user", "password")
        assert sessions["first"].verify is False
        assert sessions["first"].cookies.get("session") == "cookie-value"
        assert sessions["first"].params["key"] == "value"
        assert sessions["first"].max_redirects == 5
        assert sessions["first"].headers["X-Test"] == "header-value"
        assert sessions["first"].adapters["https://"] is provider._session.adapters["https://"]

    def test_auth_and_header_rotation_reaches_existing_thread_session(self):
        provider = FakeProvider()
        provider._session.auth = ("first", "password")
        session = provider.get_session()

        provider._session.auth = ("second", "password")
        provider._session.headers["X-Rotated"] = "yes"

        assert provider.get_session() is session
        assert session.auth == ("second", "password")
        assert session.headers["X-Rotated"] == "yes"

    def test_provider_pool_params_are_applied(self):
        provider = FakeProvider(params={"pool_connections": 4, "pool_maxsize": 7})

        adapter = provider._session.adapters["https://"]

        assert adapter._pool_connections == 4
        assert adapter._pool_maxsize == 7

    def test_bulk_run_sizes_pool_for_worker_count(self, tmp_path):
        provider = FakeProvider()
        one = artifact("one")
        register(provider, one)

        asyncio.run(finder_with(provider).download_artifacts(
            [ArtifactRequest(one)], tmp_path, max_workers=16))

        adapter = provider._session.adapters["https://"]
        assert adapter._pool_connections == 16
        assert adapter._pool_maxsize == 16

    def test_configure_pool_updates_existing_session_and_keeps_custom_adapters(self):
        provider = FakeProvider()
        session = provider.get_session()

        provider.configure_connection_pool(20)
        assert provider.get_session() is session
        assert session.adapters["https://"]._pool_maxsize == 20

        custom_adapter = CustomAdapter()
        provider._session.mount("https://", custom_adapter)
        provider.configure_connection_pool(30)

        assert provider._session.adapters["https://"] is custom_adapter

    def test_resized_adapter_keeps_retry_settings(self):
        provider = FakeProvider()
        retries = Retry(total=5)
        provider._session.mount("https://", HTTPAdapter(max_retries=retries))

        provider.configure_connection_pool(30)

        adapter = provider._session.adapters["https://"]
        assert adapter._pool_maxsize == 30
        assert adapter.max_retries.total == 5

    def test_retries_are_disabled_by_default(self):
        provider = FakeProvider()

        assert provider._session.adapters["https://"].max_retries.total == 0
        assert provider.timeout is None

    def test_retry_policy_is_applied_and_sets_default_timeout(self):
        provider = FakeProvider(params={"max_retries": 2})

        retry = provider._session.adapters["https://"].max_retries
        assert retry.total == 2
        assert retry.connect == 2
        assert retry.read == 2
        assert retry.status == 2
        assert retry.backoff_factor == 0.5
        assert retry.backoff_max == 8.0
        assert retry.backoff_jitter == 0.5
        assert set(retry.status_forcelist) == {408, 500, 502, 503, 504}
        assert retry.retry_after_max == 30
        assert retry.allowed_methods == frozenset({"GET", "HEAD"})
        assert retry.respect_retry_after_header is True
        assert retry.raise_on_status is False
        assert provider.timeout == 30.0

    def test_explicit_timeout_wins_when_retries_are_enabled(self):
        provider = FakeProvider(params={"max_retries": 2, "timeout": 5})

        assert provider.timeout == 5

    def test_thread_session_inherits_retry_adapter(self):
        provider = FakeProvider(params={"max_retries": 2})

        assert provider.get_session().adapters["https://"].max_retries.total == 2

    @patch('qubership_pipelines_common_library.v2.artifacts_finder.providers.aws_code_artifact.boto3.client')
    def test_aws_client_uses_standard_retries_and_timeout(self, boto_client):
        credentials = Credentials(
            region_name="us-east-1", access_key="key", secret_key="secret", session_token="token")

        AwsCodeArtifactProvider(
            credentials=credentials, domain="domain", repository="repo", params={"max_retries": 2})

        config = boto_client.call_args.kwargs["config"]
        assert config.retries == {"total_max_attempts": 3, "mode": "standard"}
        assert config.connect_timeout == 30.0
        assert config.read_timeout == 30.0

    @patch('qubership_pipelines_common_library.v2.artifacts_finder.providers.aws_code_artifact.boto3.client')
    def test_aws_client_keeps_sdk_retry_defaults_when_retries_are_disabled(self, boto_client):
        credentials = Credentials(
            region_name="us-east-1", access_key="key", secret_key="secret", session_token="token")

        AwsCodeArtifactProvider(credentials=credentials, domain="domain", repository="repo")

        config = boto_client.call_args.kwargs["config"]
        assert config.retries == {"total_max_attempts": 1, "mode": "standard"}
        assert config.connect_timeout == 60
        assert config.read_timeout == 60

    @patch('google.cloud.artifactregistry_v1.ArtifactRegistryClient')
    def test_gcp_grpc_disables_sdk_retries_when_retries_are_disabled(self, client_class):
        provider = GcpArtifactRegistryProvider(
            credentials=Credentials(google_credentials_object=Mock()), project="project",
            region_name="us", repository="repo")

        provider._list_files("parent", "filter")

        kwargs = client_class.return_value.list_files.call_args.kwargs
        assert kwargs["retry"] is None
        assert "timeout" not in kwargs

    @patch('google.cloud.artifactregistry_v1.ArtifactRegistryClient')
    def test_gcp_grpc_calls_use_retry_policy_and_timeout(self, client_class):
        provider = GcpArtifactRegistryProvider(
            credentials=Credentials(google_credentials_object=Mock()), project="project",
            region_name="us", repository="repo", params={"max_retries": 2})

        provider._list_files("parent", "filter")

        kwargs = client_class.return_value.list_files.call_args.kwargs
        assert kwargs["timeout"] == 30.0
        policy = kwargs["retry"]
        assert policy._predicate(google_exceptions.ServiceUnavailable("unavailable")) is True
        assert policy._predicate(google_exceptions.ServiceUnavailable("unavailable")) is True
        assert policy._predicate(google_exceptions.ServiceUnavailable("unavailable")) is False
        assert policy._predicate(google_exceptions.NotFound("missing")) is False

    @patch('google.cloud.artifactregistry_v1.ArtifactRegistryClient')
    def test_gcp_authorized_session_and_thread_clone_use_retry_adapter(self, _):
        authorized_session = requests.Session()
        provider = GcpArtifactRegistryProvider(
            credentials=Credentials(
                google_credentials_object=Mock(), authorized_session=authorized_session),
            project="project", region_name="us", repository="repo", params={"max_retries": 2})

        assert authorized_session.adapters["https://"].max_retries.total == 2
        assert provider.get_session().adapters["https://"].max_retries.total == 2

    def test_default_resource_filename_uses_last_url_segment(self):
        provider = FakeProvider()

        assert provider.get_resource_filename("https://repo.example/com/example/demo-1.0.0.json") == "demo-1.0.0.json"
        assert provider.get_resource_filename("ns/pkg/1.0.0/demo-1.0.0.json") == "demo-1.0.0.json"

    def test_azure_resource_filename_skips_content_suffix(self):
        provider = AzureArtifactsProvider(
            credentials=Credentials(access_token="token"), organization="org", project="project", feed="feed")

        url = ("https://pkgs.dev.azure.com/org/project/_apis/packaging/feeds/feed/maven/"
               "com.example/demo/1.0.0/demo-1.0.0.json/content?api-version=7.1-preview.1")

        assert provider.get_resource_filename(url) == "demo-1.0.0.json"

    @patch('google.cloud.artifactregistry_v1.ArtifactRegistryClient')
    def test_gcp_resource_filename_decodes_path_and_strips_download_suffix(self, _):
        provider = GcpArtifactRegistryProvider(
            credentials=Credentials(google_credentials_object=Mock()), project="project",
            region_name="us", repository="repo")

        standard = ("https://artifactregistry.googleapis.com/download/v1/projects/project/locations/us/"
                    "repositories/repo/files/com%2Fexample%2Fdemo%2F1.0.0%2Fdemo-1.0.0.json:download?alt=media")
        generic = ("https://artifactregistry.googleapis.com/download/v1/projects/project/locations/us/"
                   "repositories/repo/files/light-test-component:release-2024.4:"
                   "light-test-component-release-2024.4.json:download?alt=media")
        virtual = "https://us-maven.pkg.dev/project/repo/com/example/demo/1.0.0/demo-1.0.0.json"

        assert provider.get_resource_filename(standard) == "demo-1.0.0.json"
        assert provider.get_resource_filename(generic) == "light-test-component-release-2024.4.json"
        assert provider.get_resource_filename(virtual) == "demo-1.0.0.json"

    @patch('qubership_pipelines_common_library.v2.artifacts_finder.providers.gcp_artifact_registry.AuthorizedSession')
    @patch('google.cloud.artifactregistry_v1.ArtifactRegistryClient')
    def test_gcp_uses_supplied_authorized_session_as_template(self, _, authorized_session_cls):
        template = requests.Session()
        template.auth = ("user", "password")
        template.verify = False
        template.headers["X-Test"] = "header-value"
        new_session = Mock()
        new_session.headers = {}
        authorized_session_cls.return_value = new_session
        provider = GcpArtifactRegistryProvider(
            credentials=Credentials(google_credentials_object=Mock(), authorized_session=template),
            project="project", region_name="us", repository="repo")

        session = provider.get_session()

        assert session is new_session
        assert new_session.auth == ("user", "password")
        assert new_session.verify is False
        assert new_session.headers["X-Test"] == "header-value"


class TestBulkReportModel:

    def test_plain_string_status_is_coerced(self, tmp_path):
        result = BulkDownloadResult(request=ArtifactRequest(artifact("one")), status="downloaded",
                                    resolved_url="url", local_path=tmp_path / "one-1.0.0.json")
        report = BulkDownloadReport(results=[result])

        assert result.status == BulkDownloadStatus.DOWNLOADED
        assert report.status == BulkDownloadReportStatus.SUCCESS
        assert report.downloaded_count == 1
        assert report.to_dict()["status"] == "success"
