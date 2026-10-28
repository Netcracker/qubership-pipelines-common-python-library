import logging
from dataclasses import dataclass

import requests

from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact import Artifact
from qubership_pipelines_common_library.v2.artifacts_finder.utils.artifact_finder_utils import ArtifactFinderUtils


@dataclass(frozen=True)
class RepositoryContentBase:
    """Maven content base URL of one repository, with an optional alternative base probed after a miss."""

    url: str
    fallback_url: str | None = None


class MavenDirectResolver:
    """Resolves artifact download URLs from Maven repository layout without using registry search APIs."""

    HEAD_UNSUPPORTED_STATUSES = (405, 501)

    def __init__(self, session: requests.Session, timeout=None):
        self._session = session
        self._timeout = timeout

    @staticmethod
    def is_applicable(artifact: Artifact) -> bool:
        return bool(artifact.group_id) and bool(artifact.version) and not artifact.has_version_wildcard()

    def resolve(self, artifact: Artifact, bases: list[RepositoryContentBase]) -> list[str]:
        """Return existing artifact URLs in the order of `bases`, one URL per base at most."""
        urls = []
        for base in bases:
            url = self._resolve_in_repository(artifact, base.url)
            if not url and base.fallback_url:
                url = self._resolve_in_repository(artifact, base.fallback_url, reject_html=True)
            if url:
                urls.append(url)
        return ArtifactFinderUtils.deduplicate(urls)

    def resolve_if_applicable(self, artifact: Artifact, bases: list[RepositoryContentBase]) -> list[str] | None:
        """Return resolved URLs, or None when direct resolution does not apply or finds nothing."""
        if not bases or not self.is_applicable(artifact):
            return None
        return self.resolve(artifact, bases) or None

    def _resolve_in_repository(self, artifact: Artifact, base_url: str, reject_html: bool = False) -> str | None:
        artifact_base = f"{base_url.rstrip('/')}/{artifact.group_id.replace('.', '/')}/{artifact.artifact_id}"
        for candidate in self._candidate_urls(artifact, artifact_base):
            if self._exists(candidate, reject_html=reject_html):
                logging.info(f"Found artifact at direct URL: {candidate}")
                return candidate
        return None

    def _candidate_urls(self, artifact: Artifact, artifact_base: str) -> list[str]:
        artifact_id, version, extension = artifact.artifact_id, artifact.version, artifact.extension
        if artifact.is_snapshot():
            candidates = []
            resolved_version = self._resolve_snapshot_value(artifact, artifact_base)
            if resolved_version:
                candidates.append(f"{artifact_base}/{version}/{artifact_id}-{resolved_version}.{extension}")
            candidates.append(f"{artifact_base}/{version}/{artifact_id}-{version}.{extension}")
            return candidates
        snapshot_base_version = artifact.snapshot_base_version()
        if snapshot_base_version:
            return [
                f"{artifact_base}/{snapshot_base_version}-SNAPSHOT/{artifact_id}-{version}.{extension}",
                f"{artifact_base}/{version}/{artifact_id}-{version}.{extension}",
            ]
        return [f"{artifact_base}/{version}/{artifact_id}-{version}.{extension}"]

    def _resolve_snapshot_value(self, artifact: Artifact, artifact_base: str) -> str | None:
        base_version = artifact.snapshot_base_version()
        if not base_version:
            return None
        metadata_url = f"{artifact_base}/{artifact.version}/maven-metadata.xml"
        try:
            response = self._session.get(metadata_url, timeout=self._timeout, allow_redirects=True)
        except requests.RequestException as e:
            logging.warning(f"Could not read snapshot metadata '{metadata_url}': {e}")
            return None
        if response.status_code != 200:
            level = logging.DEBUG if response.status_code == 404 else logging.WARNING
            logging.log(level, f"Could not read snapshot metadata '{metadata_url}': HTTP {response.status_code}")
            return None
        return ArtifactFinderUtils.resolve_snapshot_version_from_metadata(response.content, base_version, artifact.extension)

    def _exists(self, url: str, reject_html: bool = False) -> bool:
        response = None
        try:
            response = self._session.head(url, timeout=self._timeout, allow_redirects=True)
            if response.status_code in self.HEAD_UNSUPPORTED_STATUSES:
                response.close()
                response = self._session.get(url, timeout=self._timeout, allow_redirects=True, stream=True)
            if response.status_code in (401, 403):
                logging.warning(f"Access to '{url}' returned HTTP {response.status_code}; check the registry credentials")
                return False
            if response.status_code != 200:
                logging.debug(f"Artifact is not available at '{url}': HTTP {response.status_code}")
                return False
            if reject_html and "text/html" in response.headers.get("Content-Type", ""):
                logging.debug(f"Skipping HTML response at '{url}'")
                return False
            return True
        except requests.RequestException as e:
            logging.warning(f"Could not check '{url}': {e}")
            return False
        finally:
            if response is not None:
                response.close()


def normalize_repository_keys(repositories: str | list[str] | None) -> list[str]:
    """Return repository keys without surrounding slashes, de-duplicated, preserving the first occurrence."""
    if not repositories:
        return []
    if isinstance(repositories, str):
        repositories = [repositories]
    if not isinstance(repositories, (list, tuple)):
        raise Exception("Artifact 'repositories' must be a repository key or a list of repository keys")
    keys = []
    for key in repositories:
        normalized = key.strip().strip("/") if isinstance(key, str) else ""
        if not normalized:
            raise Exception("Artifact 'repositories' must contain non-empty repository keys")
        keys.append(normalized)
    return ArtifactFinderUtils.deduplicate(keys)
