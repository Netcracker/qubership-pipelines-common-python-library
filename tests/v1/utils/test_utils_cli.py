import logging, unittest, click

from click.testing import CliRunner
from qubership_pipelines_common_library.v1.execution.exec_logger import ExecutionLogger
from qubership_pipelines_common_library.v1.utils.utils_cli import utils_cli, DEFAULT_CONTEXT_FILE_PATH


class TestUtilsCli(unittest.TestCase):

    def test_default_context_path(self):
        @click.command()
        @utils_cli
        def test_context_command(**kwargs):
            assert kwargs['context_path'] == DEFAULT_CONTEXT_FILE_PATH

        result = CliRunner().invoke(test_context_command, [])
        self.assertTrue(result.exit_code == 0)

    def test_logging_param(self):
        @click.command()
        @utils_cli
        def test_logging_command(**kwargs):
            assert ExecutionLogger.EXECUTION_LOG_LEVEL == logging.ERROR

        result = CliRunner().invoke(test_logging_command, ['--log-level=ERROR'])
        self.assertTrue(result.exit_code == 0)

    def test_input_params_transformation(self):
        @click.command()
        @utils_cli
        def test_input_params_command(**kwargs):
            input_params = kwargs.get('input_params')
            assert input_params['params']['test_param1'] == "qwe"
            assert input_params['params']['test_param2'] == "123"
            assert input_params['params']['systems']['test_system']['test_param'] == "test_value"
            assert input_params['params']['systems']['another_system']['another_param'] == "another_value"
            assert input_params['params']['full_name_param'] == "full_value"

            input_params_secure = kwargs.get('input_params_secure')
            assert input_params_secure['top_level_key'] == "456"
            assert input_params_secure['params']['systems']['test_system']['password'] == "test_password"
            assert input_params_secure['params']['secure_param'] == "secure_value"
            assert input_params_secure['params']['secure_param2'] == "secure_value2"

            # default context_path should be popped from params if we directly pass params
            assert kwargs.get('context_path') is None

        result = CliRunner().invoke(test_input_params_command,
                                    ['-p params.test_param1=qwe',
                                     '-p params.test_param2=123',
                                     '-p params.systems.test_system.test_param=test_value',
                                     '-p params__systems__another_system__another_param=another_value',
                                     '--input_params=params.full_name_param=full_value',
                                     '-s top_level_key=456',
                                     '-s params.systems.test_system.password=test_password',
                                     '--input_params_secure=params.secure_param=secure_value',
                                     '--input_params_secure=params__secure_param2=secure_value2',
                                     ])
        self.assertTrue(result.exit_code == 0)


if __name__ == '__main__':
    unittest.main()
