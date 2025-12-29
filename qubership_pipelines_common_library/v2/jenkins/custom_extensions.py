from pathlib import Path

from qubership_pipelines_common_library.v1.execution.exec_command import ExecutionCommandExtension
from qubership_pipelines_common_library.v1.execution.exec_info import ExecutionInfo
from qubership_pipelines_common_library.v2.extensions.pipeline_data_importer import PipelineDataImporter


class JenkinsOutputParamsPipelineDataImporter(PipelineDataImporter):
    """
    Jenkins Output Params Importer:
        imports data from contracted Declarative Pipelines
        extracts output files and params of targeted pipeline into 'output' folder of this command
    """
    def import_pipeline_data(self, execution: ExecutionInfo) -> None:
        self.context.logger.info("Processing jenkins job artifacts")
        artifact_paths = self.command.jenkins_client.get_pipeline_execution_artifacts(execution)
        if artifact_paths and len(artifact_paths):
            for artifact_path in artifact_paths:
                if artifact_path == "output/params.yaml":
                    self.context.logger.info(f"Artifact with name '{artifact_path}' will be processed as output params")
                    file_path = self.context.input_param_get("paths.output.params")
                    self.command.jenkins_client.save_pipeline_execution_artifact_to_file(execution, artifact_path, file_path)
                    self.context.output_params.load(file_path)
                elif artifact_path == "output/params_secure.yaml":
                    self.context.logger.info(f"Artifact with name '{artifact_path}' will be processed as output secure params")
                    file_path = self.context.input_param_get("paths.output.params_secure")
                    self.command.jenkins_client.save_pipeline_execution_artifact_to_file(execution, artifact_path, file_path)
                    self.context.output_params_secure.load(file_path)
                else:
                    self.context.logger.info(f"Artifact with name '{artifact_path}' will be saved as output file")
                    file_path = Path(self.context.input_param_get("paths.output.files")).joinpath(artifact_path)
                    self.command.jenkins_client.save_pipeline_execution_artifact_to_file(execution, artifact_path, file_path)
        else:
            self.context.logger.info("No artifacts found in the job")


class JenkinsSaveInjectedEnvVars(ExecutionCommandExtension):
    """
    Post-execution extension, saving injected environment variables from the build
    """

    INJECTED_ENV_VARS_URL = "injectedEnvVars/api/json"

    def execute(self):
        import os, requests
        from requests.auth import HTTPBasicAuth

        self.context.logger.info("Trying to get and save injected vars from build")
        build_url = self.command.execution_info.get_url()
        if build_url:
            injected_api_url = build_url + self.INJECTED_ENV_VARS_URL
            response = requests.get(injected_api_url,
                                    auth=HTTPBasicAuth(self.context.input_param_get("systems.jenkins.username"),
                                                       self.context.input_param_get("systems.jenkins.password")),
                                    verify=True if os.getenv('PYTHONHTTPSVERIFY', '1') == '0' else False)

            if response.status_code == 200:
                self.context.output_param_set("params.build.injected_vars", response.json().get("envMap", {}))
                self.context.output_params_save()
            else:
                self.context.logger.warning(f"Can't get injected variables for url {injected_api_url} with response code {response.status_code}")
        else:
            self.context.logger.warning("Can't get build url for injectedEnvVars")
