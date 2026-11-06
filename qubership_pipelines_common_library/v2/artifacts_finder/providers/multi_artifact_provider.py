import logging
import threading

from pathlib import Path
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact import Artifact
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact_provider import ArtifactProvider, ArtifactSearchResult


class MultiArtifactProvider(ArtifactProvider):
    """Treat an ordered list of providers as one provider.

    Searches return the first non-empty result. A provider failure is skipped; when no provider resolves and at
    least one failed, the error lists every failure. Downloads use the provider that resolved the URL, or try
    providers in order when the URL is unknown.
    """

    def __init__(self, providers: list[ArtifactProvider], **kwargs):
        super().__init__(**kwargs)
        if not providers or any(provider is None for provider in providers):
            raise ValueError("MultiArtifactProvider requires at least one provider")
        self.providers = list(providers)
        self._resolved_providers: dict[str, ArtifactProvider] = {}
        self._resolved_providers_lock = threading.Lock()

    def search_artifacts(self, artifact: Artifact, latest: bool = False, comparer=None, **kwargs) -> ArtifactSearchResult:
        errors = []
        for provider in self.providers:
            try:
                result = provider.search_artifacts(artifact=artifact, latest=latest, comparer=comparer, **kwargs)
            except Exception as e:
                if len(self.providers) == 1:
                    raise
                logging.debug("Artifact provider '%s' could not resolve '%s:%s': %s", provider.get_provider_name(), artifact.artifact_id, artifact.version, e)
                errors.append((provider, e))
                continue

            urls = list(result.urls or [])
            if urls:
                result.urls = urls
                result.provider = provider
                self._remember_resolved_urls(urls, provider)
                return result
            logging.debug("Artifact '%s:%s' not found in provider '%s'", artifact.artifact_id, artifact.version, provider.get_provider_name())

        if errors:
            raise Exception(self._aggregate_resolution_error(artifact, errors))
        return ArtifactSearchResult()

    def download_artifact(self, resource_url: str, local_path: str | Path, **kwargs) -> None:
        candidates = self._download_candidates(resource_url)
        errors = []
        for provider in candidates:
            try:
                result = provider.download_artifact(resource_url=resource_url, local_path=local_path, **kwargs)
                self._remember_resolved_urls([resource_url], provider)
                return result
            except Exception as e:
                if len(candidates) == 1:
                    raise
                logging.debug("Artifact provider '%s' could not download '%s': %s", provider.get_provider_name(), resource_url, e)
                errors.append((provider, e))
        raise Exception(self._aggregate_download_error(resource_url, errors))

    def get_provider_name(self) -> str:
        return "multiartifact"

    def get_resource_filename(self, resource_url: str) -> str:
        provider = self._cached_provider(resource_url)
        return provider.get_resource_filename(resource_url) if provider else super().get_resource_filename(resource_url)

    def configure_connection_pool(self, max_connections: int) -> None:
        for provider in self.providers:
            provider.configure_connection_pool(max_connections)

    def _remember_resolved_urls(self, urls: list[str], provider: ArtifactProvider) -> None:
        with self._resolved_providers_lock:
            for url in urls:
                self._resolved_providers.setdefault(url, provider)

    def _cached_provider(self, resource_url: str) -> ArtifactProvider | None:
        with self._resolved_providers_lock:
            return self._resolved_providers.get(resource_url)

    def _download_candidates(self, resource_url: str) -> list[ArtifactProvider]:
        cached = self._cached_provider(resource_url)
        return [cached] if cached is not None else list(self.providers)

    @staticmethod
    def _aggregate_resolution_error(artifact: Artifact, errors: list[tuple[ArtifactProvider, Exception]]) -> str:
        details = "\n".join(f"- {provider.get_provider_name()}: {error}" for provider, error in errors)
        return f"Could not resolve '{artifact.artifact_id}:{artifact.version}' in any configured provider:\n{details}"

    @staticmethod
    def _aggregate_download_error(resource_url: str, errors: list[tuple[ArtifactProvider, Exception]]) -> str:
        details = "\n".join(f"- {provider.get_provider_name()}: {error}" for provider, error in errors)
        return f"Could not download '{resource_url}' with any configured provider:\n{details}"
