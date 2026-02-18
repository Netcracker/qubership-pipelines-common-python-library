from abc import ABC, abstractmethod
from typing import Any


class SecretProvider(ABC):
    """Base class for all secret providers"""

    @abstractmethod
    def read_secret(self, path: str) -> dict[str, Any] | str:
        pass

    @abstractmethod
    def create_or_update_secret(self, path: str, data: dict) -> Any:
        pass

    @abstractmethod
    def delete_secret(self, path: str) -> Any:
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        pass
