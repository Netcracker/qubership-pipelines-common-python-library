from abc import ABC, abstractmethod

from qubership_pipelines_common_library.v2.artifacts_finder.model.credentials import Credentials


class CloudCredentialsProvider(ABC):
    """Base class for all cloud credentials"""

    @abstractmethod
    def get_credentials(self) -> Credentials:
        pass

    def validate_mandatory_attrs(self, attrs_names) -> None:
        missing_attrs = [attr for attr in attrs_names if getattr(self, attr, None) is None]
        if missing_attrs:
            raise ValueError(f"The following mandatory attributes are not set: {', '.join(missing_attrs)}")
