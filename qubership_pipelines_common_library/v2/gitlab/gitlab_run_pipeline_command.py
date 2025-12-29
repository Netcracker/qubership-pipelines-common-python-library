from qubership_pipelines_common_library.v1.execution.exec_command import ExecutionCommand
from qubership_pipelines_common_library.v1.execution.exec_info import ExecutionInfo
from qubership_pipelines_common_library.v1.utils.utils_string import UtilsString
from qubership_pipelines_common_library.v2.extensions.pipeline_data_importer import PipelineDataImporter
from qubership_pipelines_common_library.v2.gitlab.gitlab_pipeline_data_importer import DefaultGitlabPipelineDataImporter
from qubership_pipelines_common_library.v2.gitlab.safe_gitlab_client import SafeGitlabClient


class GitlabRunPipeline(ExecutionCommand):
    """
    Runs GitLab Pipeline via Trigger or Create API and optionally imports artifacts.

    This command runs GitLab Pipeline, monitors its execution, and provides
    options for importing resulting artifacts and custom data processing through extensible
    importers.

    Input Parameters Structure (this structure is expected inside "input_params.params" block):
    ```
    {
        "pipeline_path": "path/to/gitlab_project",               # REQUIRED: Full pipeline path (e.g. "group/subgroup/repo")
        "pipeline_branch": "main",                               # OPTIONAL: Branch to run pipeline from (default: repo's default branch)
        "trigger_type": "CREATE_PIPELINE",                       # OPTIONAL: Which API will be used to trigger the pipeline (CREATE_PIPELINE or TRIGGER_PIPELINE)
        "pipeline_params": {                                     # OPTIONAL: Input parameters to pass to the pipeline
            "KEY1": "VALUE1",
            "KEY2": "VALUE2"
        },
        "import_artifacts": false,                               # OPTIONAL: Whether to import pipeline artifacts (default: false)
        "use_existing_pipeline": 123456789,                      # OPTIONAL: Use existing pipeline ID (or use 'latest' here) instead of starting new one (debug feature)
        "timeout_seconds": 1800,                                 # OPTIONAL: Maximum wait time for pipeline completion in seconds (default: 1800, 0 for async execution)
        "wait_seconds": 1,                                       # OPTIONAL: Wait interval between status checks in seconds (default: 1)
        "retry_timeout_seconds": 180,                            # OPTIONAL: Timeout for GitLab client initialization and pipeline start retries in seconds (default: 180)
        "retry_wait_seconds": 1,                                 # OPTIONAL: Wait interval between retries in seconds (default: 1)
        "success_statuses": "SUCCESS,UNSTABLE"                   # OPTIONAL: Comma-separated list of acceptable completion statuses (default: SUCCESS)
    }
    ```

    Systems Configuration (expected in "systems.gitlab" block):
    ```
    {
        "url": "https://github.com",                             # OPTIONAL: GitLab URL for self-hosted instances (default: https://gitlab.com)
        "password": "<gitlab_token>"                             # REQUIRED: GitLab access token with CI/CD permissions
        "trigger_token": "<gitlab_trigger_token>"                # OPTIONAL: Special token issued for triggering pipeline. If not provided - will try to use CI_JOB_TOKEN
    }
    ```

    Output Parameters:
        - params.build.url: URL to view the pipeline run in GitLab
        - params.build.id: ID of the executed pipeline
        - params.build.status: Final status of the pipeline execution
        - params.build.date: Workflow start time in ISO format
        - params.build.duration: Total execution duration in human-readable format
        - params.build.name: Name of the pipeline execution

    Extension Points:
        - Custom pipeline data importers can be implemented by extending PipelineDataImporter interface
        - PipelineDataImporter is passed into constructor of command via "pipeline_data_importer" arg

    Notes:
        - Setting timeout_seconds to 0 enables asynchronous execution (workflow starts but command doesn't wait for completion)
        - For self-hosted GitLab instances, configure "systems.github.url"
        - Custom data importers receive the command context and can implement advanced processing logic
    """

    # default timeout values
    WAIT_TIMEOUT = 1800
    WAIT_SECONDS = 1
    RETRY_TIMEOUT_SECONDS = 180
    RETRY_WAIT_SECONDS = 1

    TRIGGER_TYPE_TRIGGER_PIPELINE = 'TRIGGER_PIPELINE'
    TRIGGER_TYPE_CREATE_PIPELINE = 'CREATE_PIPELINE'
    TRIGGER_TYPES = (TRIGGER_TYPE_TRIGGER_PIPELINE, TRIGGER_TYPE_CREATE_PIPELINE,)

    def __init__(self, *args, pipeline_data_importer: PipelineDataImporter = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.pipeline_data_importer = pipeline_data_importer or DefaultGitlabPipelineDataImporter()
        if pipeline_data_importer and not isinstance(pipeline_data_importer, PipelineDataImporter):
            raise TypeError(f"Class {type(pipeline_data_importer)} must inherit from PipelineDataImporter")

    def _validate(self):
        names = [
            "paths.input.params",
            "paths.output.params",
            "paths.output.files",
            "systems.gitlab.password",
            "params.pipeline_path",
        ]
        if not self.context.validate(names):
            return False

        self.timeout_seconds = max(0, int(self.context.input_param_get("params.timeout_seconds", self.WAIT_TIMEOUT)))
        self.wait_seconds = max(1, int(self.context.input_param_get("params.wait_seconds", self.WAIT_SECONDS)))

        self.retry_timeout_seconds = int(self.context.input_param_get("params.retry_timeout_seconds", self.RETRY_TIMEOUT_SECONDS))
        self.retry_wait_seconds = int(self.context.input_param_get("params.retry_wait_seconds", self.RETRY_WAIT_SECONDS))

        if self.timeout_seconds == 0:
            self.context.logger.info(f"Timeout is set to: {self.timeout_seconds}. This means that the pipeline will be started asynchronously")

        self.gitlab_url = self.context.input_param_get("systems.gitlab.url", "https://gitlab.com")
        self.pipeline_path = self.context.input_param_get("params.pipeline_path").strip("/")
        self.pipeline_branch = self.context.input_param_get("params.pipeline_branch")

        self.trigger_type = self.context.input_param_get("params.trigger_type", self.TRIGGER_TYPE_CREATE_PIPELINE)
        if self.trigger_type not in self.TRIGGER_TYPES:
            self.context.logger.error(f"Unsupported trigger_type: {self.trigger_type}")
            return False
        if self.trigger_type == self.TRIGGER_TYPE_TRIGGER_PIPELINE:
            self.trigger_token = self.context.input_param_get("systems.gitlab.trigger_token")

        self.pipeline_params = self.context.input_param_get("params.pipeline_params", {})
        if not self.pipeline_params:
            self.context.logger.info("Pipeline parameters were not specified. This means that pipeline will be started with its default values")
        if not isinstance(self.pipeline_params, dict):
            self.context.logger.error("Pipeline parameters were not loaded correctly. Probably mistake in the params definition")
            return False
        self.import_artifacts = UtilsString.convert_to_bool(self.context.input_param_get("params.import_artifacts", False))
        self.success_statuses = [x.strip() for x in self.context.input_param_get("params.success_statuses", ExecutionInfo.STATUS_SUCCESS).split(",")]
        self.use_existing_pipeline = self.context.input_param_get("params.use_existing_pipeline")
        return True

    def _execute(self):
        self.context.logger.info("Running gitlab-run-pipeline...")

        self.gl_client = SafeGitlabClient.create_gitlab_client(
            host=self.gitlab_url,
            username="",
            password=self.context.input_param_get("systems.gitlab.password"),
            retry_timeout_seconds=self.retry_timeout_seconds,
            retry_wait_seconds=self.retry_wait_seconds
        )
        self.context.logger.info("Successfully initialized GitLab client")

        if not self.pipeline_branch:
            self.pipeline_branch = self.gl_client.get_default_branch(project_id=self.pipeline_path)

        if self.use_existing_pipeline: # work with existing pipeline run
            if self.use_existing_pipeline == 'latest':
                pipeline_id = self.gl_client.get_latest_pipeline_id(project_id=self.pipeline_path, ref=self.pipeline_branch)
            else:
                pipeline_id = self.use_existing_pipeline
            self.context.logger.info(f"Using existing pipeline: {pipeline_id}")
            execution = ExecutionInfo().with_name(self.pipeline_path).with_id(pipeline_id).with_status(ExecutionInfo.STATUS_UNKNOWN)
            execution.start()
        else:
            if self.trigger_type == self.TRIGGER_TYPE_CREATE_PIPELINE:
                execution = self.gl_client.create_pipeline(
                    project_id=self.pipeline_path,
                    ref=self.pipeline_branch,
                    variables=self.pipeline_params,
                    retry_timeout_seconds=self.retry_timeout_seconds,
                    retry_wait_seconds=self.retry_wait_seconds
                )
            elif self.trigger_type == self.TRIGGER_TYPE_TRIGGER_PIPELINE:
                 execution = self.gl_client.trigger_pipeline(
                     project_id=self.pipeline_path,
                     ref=self.pipeline_branch,
                     trigger_token=self.trigger_token,
                     variables=self.pipeline_params,
                     use_ci_job_token=(self.trigger_token is None),
                     retry_timeout_seconds=self.retry_timeout_seconds,
                     retry_wait_seconds=self.retry_wait_seconds
                 )

        if execution.get_status() != ExecutionInfo.STATUS_IN_PROGRESS:
            self._exit(False, f"Pipeline was not started. Status {execution.get_status()}")
        elif self.timeout_seconds < 1:
            self.context.logger.info("Pipeline was started in asynchronous mode. Pipeline status and artifacts will not be processed")
            return

        self.context.logger.info(f"Pipeline successfully started. Waiting {self.timeout_seconds} seconds for execution to complete")
        execution = self.gl_client.wait_pipeline_execution(execution=execution, timeout_seconds=self.timeout_seconds,
                                                           wait_seconds=self.wait_seconds)
        self.context.logger.info(f"Pipeline status: {execution.get_status()}")

        if self.import_artifacts and self.pipeline_data_importer and execution.get_status() in ExecutionInfo.STATUSES_COMPLETE:
            try:
                self.pipeline_data_importer.with_command(self)
                self.pipeline_data_importer.import_pipeline_data(execution)
            except Exception as e:
                self.context.logger.error(f"Exception during pipeline_data_importer execution: {e}")

        self._save_execution_info(execution)
        if execution.get_status() not in self.success_statuses:
            self._exit(False, f"Status: {execution.get_status()}")

    def _save_execution_info(self, execution: ExecutionInfo):
        self.context.logger.info("Writing GitLab pipeline execution status")
        self.context.output_param_set("params.build.url", execution.get_url())
        self.context.output_param_set("params.build.id", execution.get_id())
        self.context.output_param_set("params.build.status", execution.get_status())
        self.context.output_param_set("params.build.date", execution.get_time_start().isoformat())
        self.context.output_param_set("params.build.duration", execution.get_duration_str())
        self.context.output_param_set("params.build.name", execution.get_name())
        self.context.output_params_save()
