from abc import ABC, abstractmethod
from typing import Any, Optional
from urllib.parse import urlparse


class SecretProvider(ABC):
    """Base class for all secret providers"""

    def __init__(self, **kwargs):
        super().__init__()

    @abstractmethod
    def read_secret(self, path: str) -> dict[str, Any] | str:
        pass

    @abstractmethod
    def create_secret(self, path: str, data: dict) -> Any:
        pass

    @abstractmethod
    def update_secret(self, path: str, data: dict) -> Any:
        pass

    @abstractmethod
    def delete_secret(self, path: str) -> Any:
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        pass

    @abstractmethod
    def secret_exists(self, path: str) -> bool:
        pass

    def parse_vals_path(self, vals_path: str) -> tuple[str, Optional[str]]:
        provider = None
        secret_path = vals_path
        fragment = None

        if "://" in vals_path:
            parsed = urlparse(vals_path)
            if "+" in parsed.scheme:
                provider = parsed.scheme.split("+", 1)[1]
            netloc = parsed.hostname or ""
            path = parsed.path or ""
            secret_path = (netloc + path).lstrip("/")
            if parsed.fragment:
                fragment = parsed.fragment.lstrip("#").lstrip("/")
        elif "#" in vals_path:
            path_part, frag_part = vals_path.split("#", 1)
            secret_path = path_part.rstrip("/")
            fragment = frag_part.lstrip("#").lstrip("/")

        if provider and provider != self.get_provider_name():
            raise Exception(f"Path implies provider {provider}, but is passed into {self.get_provider_name()}")
        return secret_path, fragment

    @staticmethod
    def get_frag_value(data: dict, frag: str) -> Any:
        """Gets nested value."""
        if not frag or not data:
            return None

        keys = [k for k in frag.split("/") if k]
        current = data
        for key in keys:
            if not isinstance(current, dict) or key not in current:
                return None
            current = current[key]
        return current

    @staticmethod
    def set_frag_value(data: dict, frag: str, value: Any) -> dict:
        """Sets nested value. Creates intermediate dicts if necessary. Returns a new dict."""
        keys = [k for k in frag.split("/") if k]
        if not keys:
            raise ValueError("Empty fragment")
        new_data = data.copy()
        current = new_data
        for key in keys[:-1]:
            if key not in current or not isinstance(current[key], dict):
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value
        return new_data

    @staticmethod
    def delete_frag_value(data: dict, frag: str) -> dict:
        """Deletes nested key. Raises KeyError if the path does not exist."""
        keys = [k for k in frag.split("/") if k]
        if not keys:
            raise ValueError("Empty fragment")
        new_data = data.copy()
        current = new_data
        for key in keys[:-1]:
            if key not in current or not isinstance(current[key], dict):
                raise KeyError(f"Key '{key}' not found in secret (path: '{frag}')")
            current = current[key]
        if keys[-1] not in current:
            raise KeyError(f"Fragment '{frag}' not found in secret")
        del current[keys[-1]]
        return new_data

    @staticmethod
    def is_non_scalar(data: Any) -> bool:
        return isinstance(data, dict) or isinstance(data, list) or isinstance(data, tuple)
