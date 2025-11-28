import logging

from qubership_pipelines_common_library.v1.execution.exec_info import ExecutionInfo
from qubership_pipelines_common_library.v1.gitlab_client import GitlabClient as GitlabClientV1


class GitlabClient(GitlabClientV1):

    def trigger_pipeline(self, project_id: str, ref: str, token: str, variables: dict):
        variables = {k: self._cast_to_string(v) for k, v in variables.items()}
        project = self.gl.projects.get(project_id, lazy=True)
        # todo le: think whether we need another token here - yeap, special trigger_token
        # fix variables = None NPE, make some dict here
        # need context parameters:
        #   to pass trigger token (test with your free-gitlab-generated-token)
        #   to select trigger/create mode
        #   to use CI_JOB_TOKEN from env as trigger token (it should be handled in client)

        #pipeline = project.trigger_pipeline(ref, token, variables)
        pipeline = project.trigger_pipeline(ref, token, variables)
        logging.info(f"Pipeline successfully started (via TRIGGER) at {pipeline.web_url}")
        return ExecutionInfo().with_name(project_id).with_id(pipeline.get_id()) \
            .with_url(pipeline.web_url).with_params(variables) \
            .start()

    def create_pipeline(self, project_id: str, ref: str, variables: dict):
        """"""
        create_data = {
            'ref': ref,
            'variables': [{'key': k, 'value': self._cast_to_string(v)} for k, v in variables.items()],
        }
        project = self.gl.projects.get(project_id, lazy=True)
        pipeline = project.pipelines.create(create_data)
        logging.info(f"Pipeline successfully started (via CREATE) at {pipeline.web_url}")
        return ExecutionInfo().with_name(project_id).with_id(pipeline.get_id()) \
            .with_url(pipeline.web_url).with_params(variables) \
            .start()
