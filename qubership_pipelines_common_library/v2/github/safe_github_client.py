from qubership_pipelines_common_library.v1.execution.exec_info import ExecutionInfo
from qubership_pipelines_common_library.v2.github.github_client import GithubClient
from qubership_pipelines_common_library.v2.utils.retry_decorator import RetryDecorator


class SafeGithubClient(GithubClient):

    def __init__(self, api_url: str, token: str):
        super().__init__(api_url=api_url, token=token)

    @classmethod
    @RetryDecorator(condition_func=lambda result: result is not None)
    def create_github_client(cls, api_url: str, token, retry_timeout_seconds: int = 180, retry_wait_seconds: int = 1):
        return cls(api_url=api_url, token=token)

    @RetryDecorator(
        condition_func=lambda result: result is not None and result.get_status() not in [
            ExecutionInfo.STATUS_NOT_STARTED, ExecutionInfo.STATUS_UNKNOWN]
    )
    def trigger_workflow(self, owner: str, repo_name: str, workflow_file_name: str, branch: str,
                         pipeline_params, retry_timeout_seconds: int = 180, retry_wait_seconds: int = 1):
        return super().trigger_workflow(owner=owner, repo_name=repo_name,
                                        workflow_file_name=workflow_file_name,
                                        branch=branch, pipeline_params=pipeline_params)
