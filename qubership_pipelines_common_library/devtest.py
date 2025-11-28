import logging, sys, os

from qubership_pipelines_common_library.v1.execution.exec_command import ExecutionCommandExtension
from qubership_pipelines_common_library.v1.utils.utils_file import UtilsFile
from qubership_pipelines_common_library.v2.gitlab.custom_extensions import GitlabModulesOpsPipelineDataImporter
from qubership_pipelines_common_library.v2.gitlab.gitlab_run_pipeline_command import GitlabRunPipeline

logging.basicConfig(level=logging.INFO, stream=sys.stdout, format=u'[%(asctime)s] [%(levelname)-5s] [class=%(filename)s:%(lineno)-3s] %(message)s')


class FunnyPreExt(ExecutionCommandExtension):
    def execute(self):
        self.context.logger.info("HI, I'M A PRE-EXTENSION")
        # self.context.logger.info(f"something: {self.command.context.}")
        # self.command._exit(True, "cool")


class FunnyPostExt(ExecutionCommandExtension):
    def execute(self):
        self.context.logger.info("HI, I'M A POST-EXTENSION")
        import uuid
        self.context.output_param_set("params.not_build.post_ext_param", str(uuid.uuid4()))
        self.context.output_params_save()


if __name__ == '__main__':
    exec_dir = 'x_devtest_dir'
    os.chdir("..")
    UtilsFile.create_exec_dir(exec_dir)
    try:
        pass
        # gl = GitlabClient("https://gitlab.com", "qwe", os.getenv("GITLAB_DEVTEST_TOKEN"))
        # project_id = "cse-test/standalone-pipeline-executor-example"
        # ref = "main"

        # execution_info_create = gl.create_pipeline(project_id, ref, {"keee": "valuee"})
        # logging.info(f"execution_info_create: {execution_info_create}")

        # execution_info_trigger = gl.trigger_pipeline(project_id, ref, os.getenv("GITLAB_DEVTEST_TRIGGER_TOKEN"), {"keee": "valuee"})
        # execution_info_trigger = gl.create_pipeline(project_id, ref,{"keee": "valuee"})
        # logging.info(f"execution_info_trigger: {execution_info_trigger}")

        cmd = GitlabRunPipeline(folder_path=exec_dir, input_params={
            "params": {
                "pipeline_path": "cse-test/standalone-pipeline-executor-example",
                # "retry_timeout_seconds": 1,
                "wait_seconds": 5,
                "trigger_type": "TRIGGER_PIPELINE",
                # "timeout_seconds": 0, # "just_trigger_it" mode
                # "pipeline_branch": "qweqwe",
                "use_existing_pipeline": 'latest',
                "import_artifacts": True,
            }
        }, input_params_secure={
            "systems": {
                "gitlab": {
                    "password": os.getenv("GITLAB_DEVTEST_TOKEN"),
                    "trigger_token": os.getenv("GITLAB_DEVTEST_TRIGGER_TOKEN"),
                }
            }
        }, pre_execute_actions=[FunnyPreExt()],
            post_execute_actions=[FunnyPostExt()],
            pipeline_data_importer=GitlabModulesOpsPipelineDataImporter())
        cmd.run()
    except ValueError as e:
        logging.error(f"Exception: {str(e)} - {type(e)}")

