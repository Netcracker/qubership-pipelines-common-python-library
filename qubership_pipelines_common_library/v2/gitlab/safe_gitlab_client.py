from qubership_pipelines_common_library.v1.execution.exec_info import ExecutionInfo
from qubership_pipelines_common_library.v2.gitlab.gitlab_client import GitlabClient
from qubership_pipelines_common_library.v2.utils.retry_decorator import RetryDecorator


class SafeGitlabClient(GitlabClient):

    def __init__(self, host: str, username: str, password: str):
        super().__init__(host=host, username=username, password=password)

    @classmethod
    @RetryDecorator(condition_func=lambda result: result is not None)
    def create_gitlab_client(cls, host: str, username: str, password: str,
                             retry_timeout_seconds: int = 180, retry_wait_seconds: int = 1):
        return cls(host, username, password)

    @RetryDecorator(
        condition_func=lambda result: result is not None and result.get_status() not in [
            ExecutionInfo.STATUS_NOT_STARTED, ExecutionInfo.STATUS_UNKNOWN]
    )
    def trigger_pipeline(self, project_id: str, ref: str, trigger_token: str = None, variables: dict = None,
                         use_ci_job_token: bool = False, retry_timeout_seconds: int = 180, retry_wait_seconds: int = 1):
        return super().trigger_pipeline(project_id=project_id, ref=ref, trigger_token=trigger_token,
                                        variables=variables, use_ci_job_token=use_ci_job_token)

    @RetryDecorator(
        condition_func=lambda result: result is not None and result.get_status() not in [
            ExecutionInfo.STATUS_NOT_STARTED, ExecutionInfo.STATUS_UNKNOWN]
    )
    def create_pipeline(self, project_id: str, ref: str, variables: dict = None,
                         retry_timeout_seconds: int = 180, retry_wait_seconds: int = 1):
        return super().create_pipeline(project_id=project_id, ref=ref, variables=variables)
