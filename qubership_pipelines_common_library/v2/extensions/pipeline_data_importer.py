from abc import ABC, abstractmethod

from qubership_pipelines_common_library.v1.execution.exec_command import ExecutionCommand
from qubership_pipelines_common_library.v1.execution.exec_info import ExecutionInfo


class PipelineDataImporter(ABC):
    """
    Base interface used by "GitHub/GitLab Run Workflow" commands
    Can be extended by users to perform custom artifacts transformations at the end of workflow
    """

    def __init__(self):
        self.context = None
        self.command = None

    def with_command(self, command: ExecutionCommand):
        self.command = command
        self.context = command.context

    @abstractmethod
    def import_pipeline_data(self, execution: ExecutionInfo) -> None:
        """Implements custom data import logic"""
        pass
