import zipfile
from pathlib import Path

from qubership_pipelines_common_library.v1.execution.exec_info import ExecutionInfo
from qubership_pipelines_common_library.v2.extensions.pipeline_data_importer import PipelineDataImporter


class DefaultGitlabPipelineDataImporter(PipelineDataImporter):
    """
    Default GitLab implementation:
        downloads all available workflow run artifacts,
        extracts them into context-defined 'paths.output.files' path
    """
    def import_pipeline_data(self, execution: ExecutionInfo) -> None:
        self.context.logger.info("DefaultGitlabPipelineDataImporter - importing pipeline data...")
        project_id = execution.get_name()
        pipeline_id = execution.get_id()
        if job := self.command.gl_client.get_latest_job(project_id, pipeline_id):
            if artifacts_file := self.command.gl_client.download_job_artifacts(job.pipeline.get('project_id'), job.id, self.context.path_temp):
                output_path = Path(self.context.input_param_get("paths.output.files"))
                output_path.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(artifacts_file) as zf:
                    self.context.logger.debug(f"Zip contents: ${zf.namelist()}")
                    zf.extractall(output_path)
        else:
            self.context.logger.warning(f"Job not found! project_id: {project_id}, pipeline_id: {pipeline_id}")
