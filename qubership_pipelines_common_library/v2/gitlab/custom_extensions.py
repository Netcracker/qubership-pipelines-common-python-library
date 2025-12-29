from pathlib import Path

from qubership_pipelines_common_library.v1.execution.exec_command import ExecutionCommandExtension
from qubership_pipelines_common_library.v1.execution.exec_info import ExecutionInfo
from qubership_pipelines_common_library.v2.extensions.pipeline_data_importer import PipelineDataImporter


class GitlabDOBPParamsPreExt(ExecutionCommandExtension):
    """
    Pre-execution extension, enriching 'pipeline_params' with values from environment variables
    """
    def execute(self):
        self.context.logger.info("Adding DOBP-specific params to pipeline_params...")

        # Add upstream-cancelled params:
        import os
        if project_url := os.getenv('PROJECT_URL'):
            from urllib.parse import urlparse
            parsed_project_url = urlparse(project_url)
            self.command.pipeline_params.setdefault('DOBP_UPSTREAM_SERVER_URL', f"{parsed_project_url.scheme}://{parsed_project_url.netloc}")
            self.command.pipeline_params.setdefault('DOBP_UPSTREAM_PROJECT_PATH', parsed_project_url.path.strip('/'))

        if pipeline_id := os.getenv('PIPELINE_ID'):
            self.command.pipeline_params.setdefault('DOBP_UPSTREAM_PIPELINE_ID', pipeline_id)

        # Add retry params:
        if retry_downstream_pipeline_id := os.getenv('DOBP_RETRY_DOWNSTREAM_PIPELINE_ID'):
            self.command.pipeline_params.setdefault('DOBP_RETRY_PIPELINE_ID', retry_downstream_pipeline_id)


class GitlabModulesOpsPipelineDataImporter(PipelineDataImporter):
    """
    GitLab Modules Ops implementation:
        imports data from contracted GitLab Declarative Pipelines
        extracts output files and params of targeted pipeline into 'output' folder of this command
    """

    IMPORTED_CONTEXT_FILE = 'pipeline/output/context.yaml'

    def import_pipeline_data(self, execution: ExecutionInfo) -> None:
        import os, zipfile
        self.context.logger.info("GitlabModulesOpsPipelineDataImporter - importing pipeline data...")
        project_id = execution.get_name()
        pipeline_id = execution.get_id()

        if job := self.command.gl_client.get_latest_job(project_id, pipeline_id):
            self.context.logger.info(f"Latest job: {job.id}")
            local_dirpath = self.context.path_temp
            self.context.logger.debug(f"Contents of folder {local_dirpath}: {os.listdir(local_dirpath)}")
            if artifacts_file := self.command.gl_client.download_job_artifacts(job.pipeline.get('project_id'), job.id, local_dirpath):
                with zipfile.ZipFile(artifacts_file) as zf:
                    self.context.logger.debug(f"Zip contents: ${zf.namelist()}")
                    zf.extractall(local_dirpath)
            self.context.logger.debug(f"Contents of folder {local_dirpath} (after zip.extractall): {os.listdir(local_dirpath)}")
            self._import_downloaded_data(local_dirpath / self.IMPORTED_CONTEXT_FILE)
        else:
            self.context.logger.warning("No jobs found")

        self.context.output_params.load(self.context.context.get("paths.output.params"))
        self.context.output_params_secure.load(self.context.context.get("paths.output.params_secure"))

    def _import_downloaded_data(self, src_context_filepath: Path):
        import shutil
        from qubership_pipelines_common_library.v1.utils.utils_file import UtilsFile
        from qubership_pipelines_common_library.v1.utils.utils_dictionary import UtilsDictionary

        if src_context_filepath.is_file():
            self.context.logger.info(f"Importing from context file {src_context_filepath}")
            src_context = UtilsFile.read_yaml(src_context_filepath)
            src_base_dirpath = src_context_filepath.parent

            def get_path_from_src_context(param, default_value=None):
                if param_value := UtilsDictionary.get_by_path(src_context, param, default_value):
                    return Path(src_base_dirpath, param_value)
                return None

            for src in ('paths.output.params', 'paths.output.params_secure',):
                src_filepath = get_path_from_src_context(src)
                if src_filepath and src_filepath.is_file():
                    dst_file = self.context.context.get(src)
                    self.context.logger.info(f"Copying file {src_filepath} -> {dst_file}")
                    UtilsFile.create_parent_dirs(dst_file)
                    shutil.copyfile(src_filepath, dst_file)

            src_files_dirpath = get_path_from_src_context('paths.output.files')
            if src_files_dirpath and src_files_dirpath.is_dir():
                dst_files_dir = self.context.context.get('paths.output.files')
                self.context.logger.info(f"Copying dir {src_files_dirpath} -> {dst_files_dir}")
                shutil.copytree(src_files_dirpath, dst_files_dir, dirs_exist_ok=True)

            src_logs_dirpath = get_path_from_src_context('paths.logs', 'logs')
            for _ext in ('json', 'yaml',):
                src_exec_report_filepath = src_logs_dirpath / f"execution_report.{_ext}"
                if src_exec_report_filepath.is_file():
                    dst_exec_report_filepath = self.context.path_logs / f"nested_pipeline_report.{_ext}"
                    UtilsFile.create_parent_dirs(dst_exec_report_filepath)
                    self.context.logger.info(f"Copying file {src_exec_report_filepath} -> {dst_exec_report_filepath}")
                    shutil.copyfile(src_exec_report_filepath, dst_exec_report_filepath)

        else:
            self.context.logger.warning(f"Imported context file does not exist: {src_context_filepath}")
