import zipfile
from pathlib import Path

from qubership_pipelines_common_library.v1.execution.exec_info import ExecutionInfo
from qubership_pipelines_common_library.v2.extensions.pipeline_data_importer import PipelineDataImporter
from qubership_pipelines_common_library.v2.jenkins.jenkins_client import JenkinsClient


class DefaultJenkinsPipelineDataImporter(PipelineDataImporter):
    """
    Default Jenkins implementation:
        downloads all available workflow run artifacts as one archive,
        extracts them into context-defined 'paths.output.files' path
    """
    def import_pipeline_data(self, execution: ExecutionInfo) -> None:
        self.context.logger.info("DefaultJenkinsPipelineDataImporter - importing pipeline data...")
        artifact_paths = self.command.jenkins_client.get_pipeline_execution_artifacts(execution)
        if artifact_paths:
            self.context.logger.info(f"Job produced {len(artifact_paths)} artifact(s)")
            self.command.jenkins_client.save_pipeline_execution_artifact_to_file(
                execution,
                JenkinsClient.BUILD_ARTIFACTS_ZIP_PATH,
                self.context.path_temp / "archive.zip")
        else:
            self.context.logger.info("No artifacts found, skipping pipeline import.")

        output_path = Path(self.context.input_param_get("paths.output.files"))
        output_path.mkdir(parents=True, exist_ok=True)
        for file_path in Path(self.context.path_temp).iterdir():
            with zipfile.ZipFile(file_path) as zf:
                zf.extractall(output_path)
