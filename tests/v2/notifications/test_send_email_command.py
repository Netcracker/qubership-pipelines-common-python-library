import pytest

from unittest.mock import patch, MagicMock
from qubership_pipelines_common_library.v2.notifications.send_email_command import SendEmail


class TestSendEmail:

    REQUIRED_INPUT_PARAMS = {
        'params': {
            'email_subject': 'SUBJ-1',
            'email_body': 'Test email body',
            'email_recipients': 'example@example.com',
        },
        'systems': {
            'email': {
                'server': 'localhost',
                'port': '25',
                'user': 'example@example.com',
                'password': 'password',
            }
        }
    }

    def test_send_email_fails_without_system_params(self, caplog, tmp_path):
        with pytest.raises(SystemExit) as exit_result:
            cmd = SendEmail(folder_path=str(tmp_path))
            cmd.run()

        assert exit_result.value.code == 1
        assert "Parameter 'systems.email.server' is mandatory" in caplog.text
        assert "Parameter 'systems.email.port' is mandatory" in caplog.text

    @patch('smtplib.SMTP')
    def test_send_email_calls_smtp_send(self, smtp, tmp_path):
        smtp_client = MagicMock()
        smtp.return_value = smtp_client

        with pytest.raises(SystemExit) as exit_result:
            cmd = SendEmail(folder_path=str(tmp_path), input_params=self.REQUIRED_INPUT_PARAMS)
            cmd.run()

        smtp_client.login.assert_called_once_with("example@example.com", "password")
        smtp_client.send_message.assert_called_once()
        assert exit_result.value.code == 0
