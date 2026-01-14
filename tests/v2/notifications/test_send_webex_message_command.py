import pytest

from unittest.mock import patch, MagicMock, Mock
from qubership_pipelines_common_library.v2.notifications.send_webex_message_command import SendWebexMessage


class TestSendWebexMessage:

    REQUIRED_INPUT_PARAMS = {
        'params': {
            'webex_message': 'Test webex message',
        },
        'systems': {
            'webex': {
                'room_id': '12345',
                'token': 'password',
            }
        }
    }

    def test_send_webex_fails_without_system_params(self, caplog, tmp_path):
        with pytest.raises(SystemExit) as exit_result:
            cmd = SendWebexMessage(folder_path=str(tmp_path))
            cmd.run()

        assert exit_result.value.code == 1
        assert "Parameter 'systems.webex.room_id' is mandatory" in caplog.text
        assert "Parameter 'systems.webex.token' is mandatory" in caplog.text

    @patch('qubership_pipelines_common_library.v2.notifications.send_webex_message_command.WebexClient')
    def test_send_email_calls_smtp_send(self, webex_class_mock, caplog, tmp_path):
        webex_client = MagicMock()
        webex_class_mock.return_value = webex_client
        webex_client.send_message.return_value = MagicMock(id='12345')

        with pytest.raises(SystemExit) as exit_result:
            cmd = SendWebexMessage(folder_path=str(tmp_path), input_params=self.REQUIRED_INPUT_PARAMS)
            cmd.context.output_param_set = Mock()
            cmd.run()

        webex_client.send_message.assert_called_once()
        cmd.context.output_param_set.assert_called_once_with("params.message_id", "12345")
        assert exit_result.value.code == 0
