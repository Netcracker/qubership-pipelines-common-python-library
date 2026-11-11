import threading
from dataclasses import dataclass, field
from urllib.parse import unquote, urlparse

import requests

from pathlib import Path
from abc import ABC, abstractmethod
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from qubership_pipelines_common_library.v2.artifacts_finder.model.artifact import Artifact


@dataclass
class ArtifactSearchResult:
    urls: list[str] = field(default_factory=list)
    method: str = "search"
    provider: "ArtifactProvider | None" = None


class ArtifactProviderError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ArtifactProvider(ABC):
    """Base class for all artifact providers.

    Provider ``params`` may set ``timeout`` in seconds, ``verify``, ``pool_connections``, ``pool_maxsize``, and
    ``max_retries``. A positive ``max_retries`` enables retries for transient connection and server failures and sets
    ``timeout`` to 30 seconds when the caller leaves it unset. A value of 0 disables retries.
    """

    DEFAULT_POOL_CONNECTIONS = 10
    DEFAULT_POOL_MAXSIZE = 10
    DEFAULT_TIMEOUT = 30.0

    RETRY_METHODS = frozenset({"GET", "HEAD"})
    RETRY_STATUS_CODES = (408, 500, 502, 503, 504)
    RETRY_AFTER_MAX = 30
    RETRY_BACKOFF_FACTOR = 0.5
    RETRY_BACKOFF_MAX = 8.0
    RETRY_BACKOFF_JITTER = 0.5

    def __init__(self, params: dict = None, **kwargs):
        self.params = params if params else {}
        self._session = requests.Session()
        self._session.verify = self.params.get('verify', True)
        self._max_retries = max(0, int(self.params.get("max_retries", 0) or 0))
        self.timeout = self.params.get('timeout', None)
        if self.timeout is None and self._max_retries > 0:
            self.timeout = self.DEFAULT_TIMEOUT
        self._thread_local = threading.local()
        self._pool_connections = max(1, int(self.params.get("pool_connections", self.DEFAULT_POOL_CONNECTIONS)))
        self._pool_maxsize = max(1, int(self.params.get("pool_maxsize", self.DEFAULT_POOL_MAXSIZE)))
        self._apply_pool_settings(self._session)

    def _apply_pool_settings(self, session: requests.Session) -> None:
        for prefix in ("http://", "https://"):
            adapter = session.adapters.get(prefix)
            if type(adapter) is HTTPAdapter:
                session.mount(prefix, HTTPAdapter(
                    pool_connections=self._pool_connections,
                    pool_maxsize=self._pool_maxsize,
                    max_retries=self._retry_policy(adapter.max_retries),
                    pool_block=getattr(adapter, "_pool_block", False),
                ))

    def _retry_policy(self, existing: Retry | int | None) -> Retry | int | None:
        if self._max_retries <= 0:
            return existing
        return Retry(
            total=self._max_retries,
            connect=self._max_retries,
            read=self._max_retries,
            status=self._max_retries,
            other=0,
            backoff_factor=self.RETRY_BACKOFF_FACTOR,
            backoff_max=self.RETRY_BACKOFF_MAX,
            backoff_jitter=self.RETRY_BACKOFF_JITTER,
            status_forcelist=self.RETRY_STATUS_CODES,
            allowed_methods=self.RETRY_METHODS,
            respect_retry_after_header=True,
            retry_after_max=self.RETRY_AFTER_MAX,
            raise_on_status=False, # Return the last response after the retries are exhausted
        )

    def configure_connection_pool(self, max_connections: int) -> None:
        """Raise the shared connection pool size to at least `max_connections`"""
        max_connections = max(1, int(max_connections))
        if max_connections <= self._pool_connections and max_connections <= self._pool_maxsize:
            return
        self._pool_connections = max(self._pool_connections, max_connections)
        self._pool_maxsize = max(self._pool_maxsize, max_connections)
        self._apply_pool_settings(self._session)
        template = self._session_template()
        if template is not self._session:
            self._apply_pool_settings(template)

    @staticmethod
    def _prepare_request_url(method: str, url: str, params: dict = None) -> str:
        return requests.Request(method=method, url=url, params=params).prepare().url

    @classmethod
    def _describe_http_response(cls, response, method: str = "GET", url: str = None, params: dict = None) -> str:
        """Return a one-line request/response description for an error report."""
        request_url = getattr(getattr(response, "request", None), "url", None)
        if not isinstance(request_url, str):
            request_url = cls._prepare_request_url(method, url, params) if url else ""
        reason = getattr(response, "reason", "")
        reason = reason if isinstance(reason, str) else ""
        body = getattr(response, "text", "")
        body = body.strip().replace("\n", " ") if isinstance(body, str) else ""
        status = f"HTTP {response.status_code}" + (f" {reason}" if reason else "")
        suffix = f": {body[:300]}" if body else ""
        return f"{method} {request_url} -> {status}{suffix}"

    @classmethod
    def _http_error(cls, response, method: str = "GET", url: str = None, params: dict = None) -> ArtifactProviderError:
        return ArtifactProviderError(cls._describe_http_response(response, method, url, params), status_code=response.status_code)

    @classmethod
    def _describe_request_error(cls, error: Exception, method: str, url: str, params: dict = None) -> str:
        """Return a one-line description of a request that raised before receiving a response."""
        return f"{method} {cls._prepare_request_url(method, url, params)} failed: {error}"

    def _session_template(self) -> requests.Session:
        return self._session

    @staticmethod
    def _copy_session_settings(session: requests.Session, template: requests.Session) -> None:
        session.auth = template.auth
        session.headers.update(template.headers)
        session.cookies.update(template.cookies)
        session.params.update(template.params)
        session.hooks = {name: list(hooks) for name, hooks in template.hooks.items()}
        session.proxies.update(template.proxies)
        session.verify = template.verify
        session.cert = template.cert
        session.max_redirects = template.max_redirects
        session.trust_env = template.trust_env
        session.stream = template.stream
        session.adapters.clear()
        session.adapters.update(template.adapters)

    def _new_session(self) -> requests.Session:
        session = requests.Session()
        self._copy_session_settings(session, self._session_template())
        return session

    def get_session(self) -> requests.Session:
        """Return a session for the current thread, cloned from this provider's configured session.

        Each thread keeps its own session and cookie jar, so concurrent provider calls do not share session state.
        The clone copies the authentication, headers, cookies, params, hooks, adapters, TLS, proxy, redirect, and
        streaming settings of the template session.
        """
        session = getattr(self._thread_local, "session", None)
        if session is None:
            session = self._new_session()
            self._thread_local.session = session
        else:
            template = self._session_template()
            session.auth = template.auth
            session.headers.update(template.headers)
            session.adapters.clear()
            session.adapters.update(template.adapters)
        return session

    def generic_download(self, resource_url: str, local_path: str | Path):
        try:
            response = self.get_session().get(url=resource_url, timeout=self.timeout)
        except requests.RequestException as e:
            raise Exception(self._describe_request_error(e, "GET", resource_url)) from e
        if response.status_code >= 400:
            raise self._http_error(response, "GET", resource_url)
        with open(local_path, 'wb') as file:
            file.write(response.content)

    def get_resource_filename(self, resource_url: str) -> str:
        """Return the file name to save a downloaded resource under."""
        return unquote(urlparse(resource_url).path).rsplit("/", 1)[-1]

    @abstractmethod
    def download_artifact(self, resource_url: str, local_path: str | Path, **kwargs) -> None:
        pass

    @abstractmethod
    def search_artifacts(self, artifact: Artifact, **kwargs) -> ArtifactSearchResult:
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        pass
