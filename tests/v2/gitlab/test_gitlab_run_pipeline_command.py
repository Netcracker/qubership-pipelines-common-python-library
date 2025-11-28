import copy
import pytest
from unittest.mock import Mock, patch, call

from qubership_pipelines_common_library.v1.execution.exec_info import ExecutionInfo
from qubership_pipelines_common_library.v2.extensions.pipeline_data_importer import PipelineDataImporter
from qubership_pipelines_common_library.v2.gitlab.gitlab_run_pipeline_command import GitlabRunPipeline


class TestGitlabRunPipeline:

    REQUIRED_INPUT_PARAMS = {
        'params': {
            'pipeline_path': 'test-owner/test-repo',
        },
        'systems': {
            'gitlab': {
                'password': 'test-token'
            }
        }
    }

    def test_validation_fails_without_required_params(self, tmp_path, caplog):
        with pytest.raises(SystemExit) as exit_result:
            cmd = GitlabRunPipeline(folder_path=str(tmp_path))
            cmd.run()

        assert exit_result.value.code == 1
        assert "Parameter 'systems.gitlab.password' is mandatory" in caplog.text

    def test_validation_succeeds_with_minimal_required_params(self, tmp_path):
        input_params = copy.deepcopy(self.REQUIRED_INPUT_PARAMS)
        cmd = GitlabRunPipeline(folder_path=str(tmp_path), input_params=input_params)

        assert cmd._validate() is True

    @patch('qubership_pipelines_common_library.v2.gitlab.safe_gitlab_client.SafeGitlabClient.create_gitlab_client')
    def test_execute_with_existing_pipeline_success(self, mock_create_client, tmp_path):
        input_params = copy.deepcopy(self.REQUIRED_INPUT_PARAMS)
        input_params['params']['use_existing_pipeline'] = 'latest'

        mock_execution = Mock(spec=ExecutionInfo)
        mock_execution.get_status.return_value = ExecutionInfo.STATUS_SUCCESS
        mock_client = Mock()
        mock_create_client.return_value = mock_client
        mock_client.wait_pipeline_execution.return_value = mock_execution

        with pytest.raises(SystemExit) as exit_result:
            cmd = GitlabRunPipeline(folder_path=str(tmp_path), input_params=input_params)
            cmd._save_execution_info = Mock()
            cmd.run()

        mock_create_client.assert_called_once()
        cmd._save_execution_info.assert_called_once()
        mock_client.wait_pipeline_execution.assert_called_once()
        assert exit_result.value.code == 0

    @patch('qubership_pipelines_common_library.v2.gitlab.safe_gitlab_client.SafeGitlabClient.create_gitlab_client')
    def test_execute_async_mode_no_waiting(self, mock_create_client, tmp_path, caplog):
        input_params = copy.deepcopy(self.REQUIRED_INPUT_PARAMS)
        input_params['params']['timeout_seconds'] = 0

        mock_execution = Mock(spec=ExecutionInfo)
        mock_execution.get_status.return_value = ExecutionInfo.STATUS_IN_PROGRESS
        mock_client = Mock()
        mock_create_client.return_value = mock_client
        mock_client.create_pipeline.return_value = mock_execution

        with pytest.raises(SystemExit) as exit_result:
            cmd = GitlabRunPipeline(folder_path=str(tmp_path), input_params=input_params)
            cmd.run()

        assert exit_result.value.code == 0
        assert "Pipeline was started in asynchronous mode" in caplog.text
        mock_client.create_pipeline.assert_called_once()
        mock_client.trigger_pipeline.assert_not_called()
        mock_client.wait_pipeline_execution.assert_not_called()

    @patch('qubership_pipelines_common_library.v2.gitlab.safe_gitlab_client.SafeGitlabClient.create_gitlab_client')
    def test_execute_with_custom_data_importer(self, mock_create_client, tmp_path):
        input_params = copy.deepcopy(self.REQUIRED_INPUT_PARAMS)
        input_params['params']['import_artifacts'] = True

        mock_execution = Mock()
        mock_execution.get_status.return_value = ExecutionInfo.STATUS_IN_PROGRESS
        mock_execution_finished = Mock()
        mock_execution_finished.get_status.return_value = ExecutionInfo.STATUS_SUCCESS

        mock_client = Mock()
        mock_create_client.return_value = mock_client
        mock_client.create_pipeline.return_value = mock_execution
        mock_client.wait_pipeline_execution.return_value = mock_execution_finished

        mock_pipeline_data_importer = Mock(spec=PipelineDataImporter)

        with pytest.raises(SystemExit) as exit_result:
            cmd = GitlabRunPipeline(folder_path=str(tmp_path), input_params=input_params,
                                    pipeline_data_importer=mock_pipeline_data_importer)
            cmd._save_execution_info = Mock()
            cmd.run()

        assert exit_result.value.code == 0
        mock_client.create_pipeline.assert_called_once()
        mock_pipeline_data_importer.with_command.assert_called_once_with(cmd)
        mock_pipeline_data_importer.import_pipeline_data.assert_called_once_with(mock_execution_finished)

    def test_save_execution_info_outputs_correct_params(self, tmp_path):
        input_params = copy.deepcopy(self.REQUIRED_INPUT_PARAMS)
        cmd = GitlabRunPipeline(folder_path=str(tmp_path), input_params=input_params)

        mock_execution = Mock()
        mock_execution.get_url.return_value = "https://gitlab.com/test/repo/-/pipelines/2197602848"
        mock_execution.get_id.return_value = 123
        mock_execution.get_status.return_value = "SUCCESS"
        mock_execution.get_time_start.return_value = Mock(isoformat=Mock(return_value="2023-01-01T00:00:00"))
        mock_execution.get_duration_str.return_value = "00:01:30"
        mock_execution.get_name.return_value = "Test Workflow"
        cmd.context.output_param_set = Mock()
        cmd.context.output_params_save = Mock()

        cmd._save_execution_info(mock_execution)

        cmd.context.output_param_set.assert_has_calls([

            call("params.build.url", "https://gitlab.com/test/repo/-/pipelines/2197602848"),
            call("params.build.id", 123),
            call("params.build.status", "SUCCESS"),
            call("params.build.date", "2023-01-01T00:00:00"),
            call("params.build.duration", "00:01:30"),
            call("params.build.name", "Test Workflow")
        ], any_order=True)
        cmd.context.output_params_save.assert_called_once()
