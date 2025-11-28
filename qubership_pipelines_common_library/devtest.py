import logging, sys, os

from qubership_pipelines_common_library.v1.execution.exec_info import ExecutionInfo
from qubership_pipelines_common_library.v2.gitlab.gitlab_client import GitlabClient
from qubership_pipelines_common_library.v2.utils.file_utils import FileUtils

logging.basicConfig(level=logging.INFO, stream=sys.stdout, format=u'[%(asctime)s] [%(levelname)-5s] [class=%(filename)s:%(lineno)-3s] %(message)s')


if __name__ == '__main__':
    exec_dir = 'x_devtest_dir'
    os.chdir("..")
    FileUtils.create_exec_dir(exec_dir)
    try:
        pass
        gl = GitlabClient("https://gitlab.com", "qwe", os.getenv("GITLAB_DEVTEST_TOKEN"))
        project_id = "cse-test/standalone-pipeline-executor-example"
        ref = "main"
        #
        # execution_info_create = gl.create_pipeline(project_id, ref, {"keee": "valuee"})
        # logging.info(f"execution_info_create: {execution_info_create}")

        execution_info_trigger = gl.trigger_pipeline(project_id, ref, {"keee": "valuee"})
        logging.info(f"execution_info_trigger: {execution_info_trigger}")


        # from qubership_pipelines_common_library.v2.github.github_run_pipeline_command import GithubRunPipeline
        # cmd = GithubRunPipeline(folder_path=exec_dir, input_params={
        #     "params": {
        #         "pipeline_owner": "LightlessOne",
        #         "pipeline_repo_name": "Light-CLI",
        #         "pipeline_workflow_file_name": "test.yml",
        #         "retry_timeout_seconds": 1,
        #         "wait_seconds": 5,
        #         # "timeout_seconds": 0, # "just_trigger_it" mode
        #         # "pipeline_branch": "qweqwe",
        #         "use_existing_pipeline": 19666690380,
        #         "import_artifacts": False,
        #     }
        # }, input_params_secure={
        #     "systems": {
        #         "github": {
        #             "password": os.getenv("GITHUB_DEVTEST_TOKEN")
        #         }
        #     }
        # })
        # cmd.run()
    except Exception as e:
        logging.error(f"Exception: {str(e)} - {type(e)}")

