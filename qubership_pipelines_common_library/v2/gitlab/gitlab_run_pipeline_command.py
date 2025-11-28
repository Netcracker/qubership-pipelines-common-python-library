import os
import shutil
import sys
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import gitlab

from qubership_pipelines_common_library.v1.execution.exec_command import ExecutionCommand, ExecutionContext
from qubership_pipelines_common_library.v1.execution.exec_info import ExecutionInfo
from qubership_pipelines_common_library.v1.utils.utils_dictionary import UtilsDictionary
from qubership_pipelines_common_library.v1.utils.utils_file import UtilsFile
from qubership_pipelines_common_library.v1.utils.utils_string import UtilsString
from qubership_pipelines_common_library.v2.gitlab.safe_gitlab_client import SafeGitlabClient
from qubership_pipelines_common_library.v2.utils.crypto_utils import CryptoUtils


### MANDATORY GitlabRunPipeline params:
# Required for all executions:
#  "systems.gitlab.url",                        # DEFAULT: https://gitlab.com
#  "systems.gitlab.password",                   # example: <gitlab_token>
#  "params.pipeline_path",                      # example: path/to/gitlab_project
#  "params.pipeline_branch",                    # example: master

### OPTIONAL params:
#  "params.pipeline_params",                    # example: { "KEY1": "VALUE1", "KEY2": "VALUE2" }
#  "params.timeout_seconds",                    # DEFAULT: 1800
#  "params.wait_seconds",                       # DEFAULT: 5
#  "params.success_statuses",                   # DEFAULT: SUCCESS
#  "params.trigger_type",                       # DEFAULT: CREATE_PIPELINE
#  "params.import_artifacts",                   # DEFAULT: false
#  "params.use_existing_pipeline",              # example: latest

class GitlabRunPipeline(ExecutionCommand):
    TIMEOUT_SECONDS = 1800 # default value how many seconds to wait for pipeline execution
    WAIT_SECONDS = 1  # default value how many seconds to wait between pipeline checks
    STATUSES_COMPLETE = [ExecutionInfo.STATUS_SUCCESS, ExecutionInfo.STATUS_UNSTABLE, ExecutionInfo.STATUS_FAILED, ExecutionInfo.STATUS_ABORTED] # TODO: move to ExecutionInfo in common library
    RETRY_TIMEOUT_SECONDS = 180  # default value, how many seconds to try to init gitlab client or start pipeline
    RETRY_WAIT_SECONDS = 1  # default value, how many seconds between tries for gitlab client init or starting pipeline
    TRIGGER_TYPE_TRIGGER_PIPELINE = 'TRIGGER_PIPELINE'
    TRIGGER_TYPE_CREATE_PIPELINE = 'CREATE_PIPELINE'
    TRIGGER_TYPES = (TRIGGER_TYPE_TRIGGER_PIPELINE, TRIGGER_TYPE_CREATE_PIPELINE,)
    TRIGGER_TYPE_DEFAULT = os.getenv('GITLAB_RUN_PIPELINE_DEFAULT_TRIGGER_TYPE', TRIGGER_TYPE_CREATE_PIPELINE)

    def _validate(self):
        self.context.logger.info(
            "Input context parameters:\n%s\n%s",
            CryptoUtils.get_parameters_for_print(self.context.input_params_secure.content, True),
            CryptoUtils.get_parameters_for_print(self.context.input_params.content, False)
        )
        names = [
            "paths.input.params",
            "paths.output.params", # required since at least information about build will be saved to this file
            #"paths.output.params_secure",
            "paths.output.files",
            "systems.gitlab.url",
            # "systems.gitlab.username", # username is not required for pipeline operations, private token is passed in systems.gitlab.password
            "systems.gitlab.password",
            "params.pipeline_path",
            # "params.pipeline_branch",  # string, optional, default is default branch of gitlab project
            # "params.trigger_type",  # string, optional: CREATE_PIPELINE | TRIGGER_PIPELINE
            # "params.import_artifacts",  # bool, optional, default is 'false'
            # "params.use_existing_pipeline",  # optional, for debug, pipeline id or 'latest'
            # "params.pipeline_params": {},  # optional, since the job may have no params of can be executed with default values
            # "params.timeout_seconds": 1800,  # optional
            # "params.wait_seconds": 1  # optional
            # "params.success_statuses": 'SUCCESS, UNSTABLE' # default value is 'SUCCESS'
        ]
        if not self.context.validate(names):
            return False

        if not self.context.input_param_get("params.timeout_seconds"):
            self.timeout_seconds = GitlabRunPipeline.TIMEOUT_SECONDS
        else:
            self.timeout_seconds = max(0, int(self.context.input_param_get("params.timeout_seconds")))

        if not self.context.input_param_get("params.wait_seconds"):
            self.wait_seconds = GitlabRunPipeline.WAIT_SECONDS
        else:
            self.wait_seconds = max(1, int(self.context.input_param_get("params.wait_seconds")))

        if self.timeout_seconds == 0:
            self.context.logger.info(f"Timeout is set to: {self.timeout_seconds}. This means that pipeline will be started asynchronously")
        self.pipeline_path = self.context.input_param_get("params.pipeline_path").strip("/")
        self.pipeline_branch = self.context.input_param_get("params.pipeline_branch")

        self.trigger_type = self.context.input_param_get("params.trigger_type", self.TRIGGER_TYPE_DEFAULT)
        if self.trigger_type not in self.TRIGGER_TYPES:
            self.context.logger.error(f"Unsupported trigger_type: {self.trigger_type}")
            return False

        self.pipeline_params = self.context.input_param_get("params.pipeline_params", {})
        if not self.pipeline_params:
            self.context.logger.info(f"Pipeline parameters was not specified. This means that pipeline will be started with its default values")
        if not isinstance(self.pipeline_params, dict):
            self.context.logger.error(f"Pipeline parameters was not loaded correctly. Probably mistake in the params definition")
            return False
        self._add_upstream_canceled_params()
        self._add_retry_params()

        self.import_artifacts = UtilsString.convert_to_bool(self.context.input_param_get("params.import_artifacts", False))
        self.success_statuses = [x.strip() for x in self.context.input_param_get("params.success_statuses", ExecutionInfo.STATUS_SUCCESS).split(",")]
        self.use_existing_pipeline = self.context.input_param_get("params.use_existing_pipeline")
        return True

    def _add_upstream_canceled_params(self):
        if project_url := os.getenv('PROJECT_URL'):
            parsed_project_url = urlparse(project_url)
            self.pipeline_params.setdefault('DOBP_UPSTREAM_SERVER_URL', f"{parsed_project_url.scheme}://{parsed_project_url.netloc}")
            self.pipeline_params.setdefault('DOBP_UPSTREAM_PROJECT_PATH', parsed_project_url.path.strip('/'))
        if pipeline_id := os.getenv('PIPELINE_ID'):
            self.pipeline_params.setdefault('DOBP_UPSTREAM_PIPELINE_ID', pipeline_id)

    def _add_retry_params(self):
        if retry_downstream_pipeline_id := os.getenv('DOBP_RETRY_DOWNSTREAM_PIPELINE_ID'):
            self.pipeline_params.setdefault('DOBP_RETRY_PIPELINE_ID', retry_downstream_pipeline_id)

    def _execute(self):
        self.context.logger.info("Running gitlab-run-pipeline...")
        retry_timeout_seconds = int(
            self.context.input_param_get("params.retry_timeout_seconds", self.RETRY_TIMEOUT_SECONDS))
        retry_wait_seconds = int(self.context.input_param_get("params.retry_wait_seconds", self.RETRY_WAIT_SECONDS))
        gl_client = SafeGitlabClient.create_gitlab_client(
            host=self.context.input_param_get("systems.gitlab.url"),
            username="",
            password=self.context.input_param_get("systems.gitlab.password"),
            retry_timeout_seconds=retry_timeout_seconds,
            retry_wait_seconds=retry_wait_seconds
        )
        self.context.logger.info(f"Successfully initialized GitLab client")

        if self.use_existing_pipeline:  # for debug
            if self.use_existing_pipeline == 'latest':
                pipeline_id = gl_client.gl.projects.get(self.pipeline_path, lazy=True).pipelines.latest(ref=self.pipeline_branch).get_id()
            else:
                pipeline_id = self.use_existing_pipeline
            self.context.logger.info(f"Using existing pipeline {pipeline_id}")
            execution = ExecutionInfo().with_name(self.pipeline_path).with_id(pipeline_id).with_status(ExecutionInfo.STATUS_UNKNOWN)
            execution.start()
        else:
            if self.pipeline_branch:
                pipeline_branch = self.pipeline_branch
            else:
                pipeline_branch = gl_client.gl.projects.get(self.pipeline_path).default_branch  #TODO: change in the client
            if self.trigger_type == self.TRIGGER_TYPE_CREATE_PIPELINE:
                data = {
                        'ref': pipeline_branch,
                        'variables': [{'key': k, 'value': v} for k, v in self.pipeline_params.items()],
                }
                execution = gl_client.trigger_pipeline(
                        project_id=self.pipeline_path,
                        pipeline_params=data,
                        retry_timeout_seconds=retry_timeout_seconds,
                        retry_wait_seconds=retry_wait_seconds
                )
            elif self.trigger_type == self.TRIGGER_TYPE_TRIGGER_PIPELINE:
                execution = self._trigger_pipeline(
                        gl=gl_client.gl,
                        project_id=self.pipeline_path,
                        ref=pipeline_branch,
                        token=os.getenv('CI_JOB_TOKEN'),
                        variables=self.pipeline_params
                )

        if execution.get_status() != ExecutionInfo.STATUS_IN_PROGRESS:
            self._exit(False, f"Pipeline was not started. Status {execution.get_status()}")
        elif self.timeout_seconds < 1:
            self.context.logger.info(f"Pipeline was started in asynchronous mode. Pipeline status and artifacts will not be processed")
            self._exit(True, f"Status: {execution.get_status()}")
        else:
            self.context.logger.info(f"Pipeline successfully started. Waiting {self.timeout_seconds} seconds for execution to complete")
            execution = gl_client.wait_pipeline_execution(
                    execution=execution,
                    timeout_seconds=self.timeout_seconds,
                    break_status_list=[SafeGitlabClient.STATUS_SUCCESS, SafeGitlabClient.STATUS_FAILED, SafeGitlabClient.STATUS_CANCELLED, SafeGitlabClient.STATUS_SKIPPED], #TODO: change in the client
                    wait_seconds=retry_wait_seconds
                    #TODO change in the client: use self.wait_seconds
                    )
            self.context.logger.info(f"Pipeline status: {execution.get_status()}")
            if self.import_artifacts and execution.get_status() in GitlabRunPipeline.STATUSES_COMPLETE:
                PipelineDataImporter(gl_client.gl, self.context).import_pipeline_data(
                        project_id=self.pipeline_path,
                        pipeline_id=execution.get_id(),
                )
                self.context.output_params.load(self.context.context.get("paths.output.params"))
                self.context.output_params_secure.load(self.context.context.get("paths.output.params_secure"))

            self._save_execution_info(execution)
            self._exit(execution.get_status() in self.success_statuses, f"Status: {execution.get_status()}")

    @staticmethod
    def _cast_to_string(value):
        if isinstance(value, str): return value
        if value is None: return ''
        if isinstance(value, bool): return 'true' if value else 'false'
        return str(value)

    def _trigger_pipeline(self, gl: gitlab.Gitlab, project_id, ref: str, token: str, variables: dict):
        variables = {k: self._cast_to_string(v) for k, v in variables.items()}  # A map of key-valued strings is expected
        project = gl.projects.get(project_id, lazy=True)
        pipeline = project.trigger_pipeline(ref, token, variables)
        self.context.logger.info(f"Pipeline successfully started at {pipeline.web_url}")
        return (ExecutionInfo()
                .with_name(project_id).with_id(pipeline.get_id()).with_url(pipeline.web_url).with_params(variables)
                .start())

    def _save_execution_info(self, execution: ExecutionInfo):
        self.context.logger.info(f"Writing GitLab pipeline execution status")
        self.context.output_param_set("params.build.url", execution.get_url())
        self.context.output_param_set("params.build.id", execution.get_id())
        self.context.output_param_set("params.build.status", execution.get_status())
        self.context.output_param_set("params.build.date", execution.get_time_start().isoformat())
        self.context.output_param_set("params.build.duration", execution.get_duration_str())
        self.context.output_param_set("params.build.name", execution.get_name())
        self.context.output_params_save()

    def _exit(self, success: bool, message: str):
        if success:
            self.context.logger.info(message)
            sys.exit(0)
        else:
            self.context.logger.error(message)
            sys.exit(1)


class PipelineDataImporter:
    IMPORTED_CONTEXT_FILE = 'pipeline/output/context.yaml'

    def __init__(self, gl: gitlab.Gitlab, exec_context: ExecutionContext):
        self.gl = gl
        self.exec_context = exec_context

    def import_pipeline_data(self, project_id, pipeline_id):
        if job := self._get_latest_job(project_id, pipeline_id):
            self.exec_context.logger.info(f"Latest job: {job.id}")
            local_dirpath = self.exec_context.path_temp
            self.exec_context.logger.debug(f"Contents of folder {local_dirpath}: {os.listdir(local_dirpath)}")
            if artifacts_file := self._download_job_artifacts(job.pipeline.get('project_id'), job.id, local_dirpath):
                with zipfile.ZipFile(artifacts_file) as zf:
                    self.exec_context.logger.debug(f"Zip contents: ${zf.namelist()}")
                    zf.extractall(local_dirpath)
            self.exec_context.logger.debug(f"Contents of folder {local_dirpath} (after zip.extractall): {os.listdir(local_dirpath)}")
            self._import_downloaded_data(local_dirpath / PipelineDataImporter.IMPORTED_CONTEXT_FILE)
        else:
            self.exec_context.logger.warning(f"No jobs found")

    @staticmethod
    def _create_parent_dirs(file):
        if directory := os.path.dirname(file):
            os.makedirs(directory, exist_ok=True)

    def _get_latest_job(self, project_id, pipeline_id):
        self.exec_context.logger.info(f"Getting project by id '{project_id}'...")
        project = self.gl.projects.get(project_id, lazy=True)
        self.exec_context.logger.info(f"Getting pipeline by id '{pipeline_id}'...")
        pipeline = project.pipelines.get(pipeline_id, lazy=True)

        jobs = pipeline.jobs.list(get_all=True)
        self.exec_context.logger.info(f"All jobs from the pipeline: {jobs}")
        # get jobs from downstream pipelines
        bridges = pipeline.bridges.list(get_all=True)
        self.exec_context.logger.debug(f"Bridges: {bridges}")
        for bridge in bridges:
            downstream_pipeline_data = bridge.downstream_pipeline
            downstream_project = self.gl.projects.get(downstream_pipeline_data.get('project_id'), lazy=True)
            self.exec_context.logger.debug(f"Getting jobs from a downstream pipeline: {downstream_pipeline_data.get('id')}...")
            downstream_pipeline = downstream_project.pipelines.get(downstream_pipeline_data.get('id'))
            jobs.extend(downstream_pipeline.jobs.list(get_all=True))

        # get jobs from child pipelines
        child_pipelines = project.pipelines.list(ref=f"downstream/{pipeline_id}", source="pipeline", all=True)
        self.exec_context.logger.debug(f"Child pipelines: {child_pipelines}")
        for child_pipeline in child_pipelines:
            self.exec_context.logger.debug(f"Getting jobs from a child pipeline: {child_pipeline.id}...")
            child_jobs = child_pipeline.jobs.list(get_all=True)
            jobs.extend(child_jobs)

        self.exec_context.logger.info(f"All jobs (+ jobs from downstream pipelines): {jobs}")
        jobs = [j for j in jobs if j.started_at]
        jobs = sorted(jobs, key=lambda j: j.started_at, reverse=True)

        return jobs[0] if jobs else None

    def _download_job_artifacts(self, project_id, job_id, local_dir):
        project = self.gl.projects.get(project_id, lazy=True)
        job = project.jobs.get(job_id, lazy=True)
        local_file = Path(local_dir, f"{job_id}.zip")
        with local_file.open('wb') as f:
            try:
                job.artifacts(streamed=True, action=f.write)
            except gitlab.GitlabGetError as e:
                if e.response_code == 404:
                    self.exec_context.logger.warning(f"No artifacts for job {job_id}")
                    return None
                else: raise
        self.exec_context.logger.info(f"Artifacts downloaded to {local_file}")
        return local_file

    def _import_downloaded_data(self, src_context_filepath: Path):
        if src_context_filepath.is_file():
            self.exec_context.logger.info(f"Importing from context file {src_context_filepath}")
            src_context = UtilsFile.read_yaml(src_context_filepath)
            src_base_dirpath = src_context_filepath.parent

            def get_path_from_src_context(param, default_value=None):
                if param_value := UtilsDictionary.get_by_path(src_context, param, default_value):
                    return Path(src_base_dirpath, param_value)
                return None

            for src in ('paths.output.params', 'paths.output.params_secure',):
                src_filepath = get_path_from_src_context(src)
                if src_filepath and src_filepath.is_file():
                    dst_file = self.exec_context.context.get(src)
                    self.exec_context.logger.info(f"Copying file {src_filepath} -> {dst_file}")
                    self._create_parent_dirs(dst_file)
                    shutil.copyfile(src_filepath, dst_file)

            src_files_dirpath = get_path_from_src_context('paths.output.files')
            if src_files_dirpath and src_files_dirpath.is_dir():
                dst_files_dir = self.exec_context.context.get('paths.output.files')
                self.exec_context.logger.info(f"Copying dir {src_files_dirpath} -> {dst_files_dir}")
                shutil.copytree(src_files_dirpath, dst_files_dir, dirs_exist_ok=True)

            src_logs_dirpath = get_path_from_src_context('paths.logs', 'logs')
            for _ext in ('json', 'yaml',):
                src_exec_report_filepath = src_logs_dirpath / f"execution_report.{_ext}"
                if src_exec_report_filepath.is_file():
                    dst_exec_report_filepath = self.exec_context.path_logs / f"nested_pipeline_report.{_ext}"
                    self._create_parent_dirs(dst_exec_report_filepath)
                    self.exec_context.logger.info(
                            f"Copying file {src_exec_report_filepath} -> {dst_exec_report_filepath}")
                    shutil.copyfile(src_exec_report_filepath, dst_exec_report_filepath)

        else:
            self.exec_context.logger.warning(f"Imported context file does not exist: {src_context_filepath}")
