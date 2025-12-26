from qubership_pipelines_common_library.v1.execution.exec_command import ExecutionCommand
from qubership_pipelines_common_library.v1.execution.exec_info import ExecutionInfo
from qubership_pipelines_common_library.v1.utils.utils_string import UtilsString
from qubership_pipelines_common_library.v2.extensions.pipeline_data_importer import PipelineDataImporter
from qubership_pipelines_common_library.v2.github.github_pipeline_data_importer import DefaultGithubPipelineDataImporter
from qubership_pipelines_common_library.v2.github.safe_github_client import SafeGithubClient


class GithubRunPipeline(ExecutionCommand):
    """
    Executes a GitHub Actions workflow pipeline and optionally imports artifacts.

    This command triggers a GitHub workflow run, monitors its execution, and provides
    options for importing workflow artifacts and custom data processing through extensible
    importers.

    Input Parameters Structure (this structure is expected inside "input_params.params" block):
    ```
    {
        "pipeline_owner": "Netcracker",                          # REQUIRED: Repository owner/organization
        "pipeline_repo_name": "qubership-test-pipelines",        # REQUIRED: Repository name
        "pipeline_workflow_file_name": "test.yaml",              # REQUIRED: Workflow filename (e.g., main.yaml, ci-cd.yml)
        "pipeline_branch": "main",                               # OPTIONAL: Branch to run workflow from (default: repo's default branch)
        "pipeline_params": {                                     # OPTIONAL: Input parameters to pass to the workflow
            "KEY1": "VALUE1",
            "KEY2": "VALUE2"
        },
        "import_artifacts": false,                               # OPTIONAL: Whether to import workflow artifacts (default: false)
        "use_existing_pipeline": 123456789,                      # OPTIONAL: Use existing workflow run ID instead of starting new one (debug feature)
        "timeout_seconds": 1800,                                 # OPTIONAL: Maximum wait time for workflow completion in seconds (default: 1800, 0 for async execution)
        "wait_seconds": 1,                                       # OPTIONAL: Wait interval between status checks in seconds (default: 1)
        "retry_timeout_seconds": 180,                            # OPTIONAL: Timeout for GitHub client initialization and workflow start retries in seconds (default: 180)
        "retry_wait_seconds": 1,                                 # OPTIONAL: Wait interval between retries in seconds (default: 1)
        "success_statuses": "SUCCESS,UNSTABLE"                   # OPTIONAL: Comma-separated list of acceptable completion statuses (default: SUCCESS)
    }
    ```

    Systems Configuration (expected in "systems.github" block):
    ```
    {
        "url": "https://github.com",                             # OPTIONAL: GitHub UI URL for self-hosted instances (default: https://github.com)
        "api_url": "https://api.github.com",                     # OPTIONAL: GitHub API URL for self-hosted instances (default: https://api.github.com)
        "password": "<github_token>"                             # REQUIRED: GitHub access token with workflow permissions
    }
    ```

    Output Parameters:
        - params.build.url: URL to view the workflow run in GitHub
        - params.build.id: ID of the executed workflow run
        - params.build.status: Final status of the workflow execution
        - params.build.date: Workflow start time in ISO format
        - params.build.duration: Total execution duration in human-readable format
        - params.build.name: Name of the workflow run

    Extension Points:
        - Custom pipeline data importers can be implemented by extending PipelineDataImporter interface
        - PipelineDataImporter is passed into constructor of command via "pipeline_data_importer" arg

    Notes:
        - Setting timeout_seconds to 0 enables asynchronous execution (workflow starts but command doesn't wait for completion)
        - For self-hosted GitHub Enterprise, configure both "systems.github.url" and "systems.github.api_url"
        - Custom data importers receive the command context and can implement advanced processing logic
    """

    # default timeout values
    WAIT_TIMEOUT = 1800
    WAIT_SECONDS = 1
    RETRY_TIMEOUT_SECONDS = 180
    RETRY_WAIT_SECONDS = 1

    def __init__(self, *args, pipeline_data_importer: PipelineDataImporter = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.pipeline_data_importer = pipeline_data_importer or DefaultGithubPipelineDataImporter()
        if pipeline_data_importer and not isinstance(pipeline_data_importer, PipelineDataImporter):
            raise TypeError(f"Class {type(pipeline_data_importer)} must inherit from PipelineDataImporter")

    def _validate(self):
        names = [
            "paths.input.params",
            "paths.output.params",
            "paths.output.files",
            "systems.github.password",
            "params.pipeline_owner",
            "params.pipeline_repo_name",
            "params.pipeline_workflow_file_name",
        ]
        if not self.context.validate(names):
            return False

        self.timeout_seconds = max(0, int(self.context.input_param_get("params.timeout_seconds", self.WAIT_TIMEOUT)))
        self.wait_seconds = max(1, int(self.context.input_param_get("params.wait_seconds", self.WAIT_SECONDS)))

        self.retry_timeout_seconds = int(self.context.input_param_get("params.retry_timeout_seconds", self.RETRY_TIMEOUT_SECONDS))
        self.retry_wait_seconds = int(self.context.input_param_get("params.retry_wait_seconds", self.RETRY_WAIT_SECONDS))

        if self.timeout_seconds == 0:
            self.context.logger.info(f"Timeout is set to: {self.timeout_seconds}. This means that the pipeline will be started asynchronously")

        self.pipeline_owner = self.context.input_param_get("params.pipeline_owner")
        self.pipeline_repo_name = self.context.input_param_get("params.pipeline_repo_name")
        self.pipeline_workflow_file_name = self.context.input_param_get("params.pipeline_workflow_file_name")
        self.pipeline_branch = self.context.input_param_get("params.pipeline_branch")
        self.pipeline_params = self.context.input_param_get("params.pipeline_params", {})
        if not self.pipeline_params:
            self.context.logger.info("Pipeline parameters were not specified. This means that pipeline will be started with its default values")
        if not isinstance(self.pipeline_params, dict):
            self.context.logger.error("Pipeline parameters were not loaded correctly. Probably mistake in the params definition")
            return False
        self.import_artifacts = UtilsString.convert_to_bool(self.context.input_param_get("params.import_artifacts", False))
        self.success_statuses = [x.strip() for x in self.context.input_param_get("params.success_statuses", ExecutionInfo.STATUS_SUCCESS).split(",")]
        self.use_existing_pipeline = self.context.input_param_get("params.use_existing_pipeline")
        self.ui_url = self.context.input_param_get("systems.github.ui_url", "https://github.com")
        return True

    def _execute(self):
        self.context.logger.info("GithubRunPipeline - triggering GitHub workflow run and fetching results...")

        self.github_client = SafeGithubClient.create_github_client(
            api_url=self.context.input_param_get("systems.github.api_url"),
            token=self.context.input_param_get("systems.github.password"),
            retry_timeout_seconds=self.retry_timeout_seconds,
            retry_wait_seconds=self.retry_wait_seconds
        )

        if self.use_existing_pipeline: # work with existing workflow run
            pipeline_id = self.use_existing_pipeline
            self.context.logger.info(f"Using existing pipeline {pipeline_id}")
            execution = (ExecutionInfo()
                         .with_url(f"{self.ui_url}/{self.pipeline_owner}/{self.pipeline_repo_name}/")
                         .with_name(self.pipeline_workflow_file_name).with_id(int(pipeline_id))
                         .with_status(ExecutionInfo.STATUS_UNKNOWN))
            execution.start()
        else:
            branch = self.pipeline_branch
            if not branch:
                branch = self.github_client.get_repo_default_branch(self.pipeline_owner, self.pipeline_repo_name)
            execution = self.github_client.trigger_workflow(owner=self.pipeline_owner, repo_name=self.pipeline_repo_name,
                                                            workflow_file_name=self.pipeline_workflow_file_name,
                                                            branch=branch, pipeline_params=self.pipeline_params,
                                                            retry_timeout_seconds=self.retry_timeout_seconds,
                                                            retry_wait_seconds=self.retry_wait_seconds
                                                            )
            self.context.logger.info(f"Triggered pipeline {execution.get_id()}, status: {execution.get_status()}, url: {execution.get_url()}")

        if execution.get_status() != ExecutionInfo.STATUS_IN_PROGRESS:
            self._exit(False, f"Pipeline was not started. Status {execution.get_status()}")
        elif self.timeout_seconds < 1:
            self.context.logger.info("Pipeline was started in asynchronous mode. Pipeline status and artifacts will not be processed")
            return

        execution = self.github_client.wait_workflow_run_execution(execution=execution,
                                                                   timeout_seconds=self.timeout_seconds,
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
        self.context.logger.info("Writing GitHub workflow execution status")
        self.context.output_param_set("params.build.url", execution.get_url())
        self.context.output_param_set("params.build.id", execution.get_id())
        self.context.output_param_set("params.build.status", execution.get_status())
        self.context.output_param_set("params.build.date", execution.get_time_start().isoformat())
        self.context.output_param_set("params.build.duration", execution.get_duration_str())
        self.context.output_param_set("params.build.name", execution.get_name())
        self.context.output_params_save()
