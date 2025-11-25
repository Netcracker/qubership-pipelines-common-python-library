import logging, sys, os

from qubership_pipelines_common_library.v2.utils.file_utils import FileUtils

logging.basicConfig(level=logging.INFO, stream=sys.stdout, format=u'[%(asctime)s] [%(levelname)-5s] [class=%(filename)s:%(lineno)-3s] %(message)s')


if __name__ == '__main__':
    exec_dir = 'x_devtest_dir'
    os.chdir("..")
    FileUtils.create_exec_dir(exec_dir)
    try:
        from qubership_pipelines_common_library.v2.github.github_run_pipeline_command import GithubRunPipeline
        cmd = GithubRunPipeline(folder_path=exec_dir, input_params={
            "params": {
                "pipeline_owner": "LightlessOne",
                "pipeline_repo_name": "Light-CLI",
                "pipeline_workflow_file_name": "test.yml",
                "retry_timeout_seconds": 1,
                "wait_seconds": 5,
                # "timeout_seconds": 0, # "just_trigger_it" mode
                # "pipeline_branch": "qweqwe",
                "use_existing_pipeline": 19666690380,
                "import_artifacts": False,
            }
        }, input_params_secure={
            "systems": {
                "github": {
                    "password": os.getenv("GITHUB_DEVTEST_TOKEN")
                }
            }
        })
        cmd.run()
    except Exception as e:
        print(e)

