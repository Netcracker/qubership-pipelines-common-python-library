from qubership_pipelines_common_library.v2.jenkins.jenkins_client import JenkinsClient
from qubership_pipelines_common_library.v2.utils.retry_decorator import RetryDecorator


class SafeJenkinsClient(JenkinsClient):

    def __init__(self, host: str, user: str, password: str):
        super().__init__(host, user, password)

    @classmethod
    @RetryDecorator(condition_func=lambda result: result is not None)
    def create_jenkins_client(cls, host: str, user: str, password: str,
                              retry_timeout_seconds: int = 180, retry_wait_seconds: int = 1):
        return cls(host, user, password)
