import zipfile
from pathlib import Path

from qubership_pipelines_common_library.v1.execution.exec_info import ExecutionInfo
from qubership_pipelines_common_library.v2.extensions.pipeline_data_importer import PipelineDataImporter


class DefaultGithubPipelineDataImporter(PipelineDataImporter):
    """
    Default GitHub implementation:
        downloads all available workflow run artifacts,
        extracts them into context-defined 'paths.output.files' path
    """
    def import_pipeline_data(self, execution: ExecutionInfo) -> None:
        self.context.logger.info("DefaultGithubPipelineDataImporter - importing pipeline data...")
        self.command.github_client.download_workflow_run_artifacts(execution, self.context.path_temp)
        output_path = Path(self.context.input_param_get("paths.output.files"))
        output_path.mkdir(parents=True, exist_ok=True)
        for file_path in Path(self.context.path_temp).iterdir():
            with zipfile.ZipFile(file_path) as zf:
                zf.extractall(output_path)
