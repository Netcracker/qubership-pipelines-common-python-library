import copy
import pytest
from unittest.mock import Mock, patch, call

from qubership_pipelines_common_library.v1.execution.exec_info import ExecutionInfo
from qubership_pipelines_common_library.v2.jenkins.jenkins_run_pipeline_command import JenkinsRunPipeline


class TestJenkinsRunPipeline:

    REQUIRED_INPUT_PARAMS = {
        'params': {
            'pipeline_path': 'test-owner/test-repo',
        },
        'systems': {
            'jenkins': {
                'url': 'http://localhost:8080',
                'username': 'test-user',
                'password': 'test-token'
            }
        }
    }

    def test_validation_fails_without_required_params(self, tmp_path, caplog):
        with pytest.raises(SystemExit) as exit_result:
            cmd = JenkinsRunPipeline(folder_path=str(tmp_path))
            cmd.run()

        assert exit_result.value.code == 1
        assert "Parameter 'systems.jenkins.password' is mandatory" in caplog.text

    def test_validation_succeeds_with_minimal_required_params(self, tmp_path):
        input_params = copy.deepcopy(self.REQUIRED_INPUT_PARAMS)
        cmd = JenkinsRunPipeline(folder_path=str(tmp_path), input_params=input_params)

        assert cmd._validate() is True

    @patch('qubership_pipelines_common_library.v2.jenkins.safe_jenkins_client.SafeJenkinsClient.create_jenkins_client')
    def test_execute_with_existing_pipeline_success(self, mock_create_client, tmp_path):
        input_params = copy.deepcopy(self.REQUIRED_INPUT_PARAMS)
        input_params['params']['use_existing_pipeline'] = '1'

        mock_execution = Mock(spec=ExecutionInfo)
        mock_execution.get_status.return_value = ExecutionInfo.STATUS_SUCCESS
        mock_client = Mock()
        mock_create_client.return_value = mock_client
        mock_client.wait_pipeline_execution.return_value = mock_execution

        with pytest.raises(SystemExit) as exit_result:
            cmd = JenkinsRunPipeline(folder_path=str(tmp_path), input_params=input_params)
            cmd._save_execution_info = Mock()
            cmd.run()

        mock_create_client.assert_called_once()
        cmd._save_execution_info.assert_called_once()
        mock_client.wait_pipeline_execution.assert_called_once()
        assert exit_result.value.code == 0

    @patch('qubership_pipelines_common_library.v2.jenkins.safe_jenkins_client.SafeJenkinsClient.create_jenkins_client')
    def test_execute_async_mode_no_waiting(self, mock_create_client, tmp_path, caplog):
        input_params = copy.deepcopy(self.REQUIRED_INPUT_PARAMS)
        input_params['params']['timeout_seconds'] = 0

        mock_execution = Mock(spec=ExecutionInfo)
        mock_execution.get_status.return_value = ExecutionInfo.STATUS_IN_PROGRESS
        mock_client = Mock()
        mock_create_client.return_value = mock_client
        mock_client.run_pipeline.return_value = mock_execution

        with pytest.raises(SystemExit) as exit_result:
            cmd = JenkinsRunPipeline(folder_path=str(tmp_path), input_params=input_params)
            cmd.run()

        assert exit_result.value.code == 0
        assert "Pipeline was started in asynchronous mode" in caplog.text
        mock_client.run_pipeline.assert_called_once()
        mock_client.wait_pipeline_execution.assert_not_called()

    def test_save_execution_info_outputs_correct_params(self, tmp_path):
        input_params = copy.deepcopy(self.REQUIRED_INPUT_PARAMS)
        cmd = JenkinsRunPipeline(folder_path=str(tmp_path), input_params=input_params)

        mock_execution = Mock()
        mock_execution.get_url.return_value = "https://localhost:8000/test/job/2"
        mock_execution.get_id.return_value = 2
        mock_execution.get_status.return_value = "SUCCESS"
        mock_execution.get_time_start.return_value = Mock(isoformat=Mock(return_value="2023-01-01T00:00:00"))
        mock_execution.get_duration_str.return_value = "00:01:30"
        mock_execution.get_name.return_value = "Test Workflow"
        cmd.context.output_param_set = Mock()
        cmd.context.output_params_save = Mock()

        cmd._save_execution_info(mock_execution)

        cmd.context.output_param_set.assert_has_calls([

            call("params.build.url", "https://localhost:8000/test/job/2"),
            call("params.build.id", 2),
            call("params.build.status", "SUCCESS"),
            call("params.build.date", "2023-01-01T00:00:00"),
            call("params.build.duration", "00:01:30"),
            call("params.build.name", "Test Workflow")
        ], any_order=True)
        cmd.context.output_params_save.assert_called_once()
