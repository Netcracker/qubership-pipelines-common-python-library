import os, logging

from qubership_pipelines_common_library.v1.execution.exec_info import ExecutionInfo
from qubership_pipelines_common_library.v1.gitlab_client import GitlabClient as GitlabClientV1


class GitlabClient(GitlabClientV1):

    def trigger_pipeline(self, project_id: str, ref: str, trigger_token: str = None, variables: dict = None, use_ci_job_token: bool = False):
        """"""
        if variables is None:
            variables = {}
        if use_ci_job_token:
            trigger_token = os.getenv('CI_JOB_TOKEN')
        trigger_data = {k: self._cast_to_string(v) for k, v in variables.items()}
        project = self.gl.projects.get(project_id, lazy=True)
        pipeline = project.trigger_pipeline(ref, trigger_token, trigger_data)
        logging.info(f"Pipeline successfully started (via TRIGGER) at {pipeline.web_url}")
        return ExecutionInfo().with_name(project_id).with_id(pipeline.get_id()) \
            .with_url(pipeline.web_url).with_params(trigger_data) \
            .start()

    def create_pipeline(self, project_id: str, ref: str, variables: dict):
        """"""
        if variables is None:
            variables = {}
        create_data = {
            'ref': ref,
            'variables': [{'key': k, 'value': self._cast_to_string(v)} for k, v in variables.items()],
        }
        project = self.gl.projects.get(project_id, lazy=True)
        pipeline = project.pipelines.create(create_data)
        logging.info(f"Pipeline successfully started (via CREATE) at {pipeline.web_url}")
        return ExecutionInfo().with_name(project_id).with_id(pipeline.get_id()) \
            .with_url(pipeline.web_url).with_params(create_data) \
            .start()
