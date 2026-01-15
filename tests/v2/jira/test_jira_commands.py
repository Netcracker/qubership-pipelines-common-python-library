import pytest

from unittest.mock import patch, MagicMock
from qubership_pipelines_common_library.v2.jira.jira_create_ticket_command import JiraCreateTicket


class TestJiraCommands:

    REQUIRED_INPUT_PARAMS = {
        'params': {
            'ticket': {
                'fields': {
                    "project": {"key": "BUG"},
                    "issuetype": {"name": "Bug"},
                    "summary": "[QWE-123] test title",
                    "description": "Test description Updated",
                }
            },
        },
        'systems': {
            'jira': {
                'url': 'localhost',
                'username': 'test@qubership.org',
                'password': 'password',
            }
        }
    }

    def test_create_ticket_fails_without_system_params(self, caplog, tmp_path):
        with pytest.raises(SystemExit) as exit_result:
            cmd = JiraCreateTicket(folder_path=str(tmp_path))
            cmd.run()

        assert exit_result.value.code == 1
        assert "Parameter 'systems.jira.url' is mandatory" in caplog.text
        assert "Parameter 'systems.jira.password' is mandatory" in caplog.text

    @patch('qubership_pipelines_common_library.v2.jira.jira_client.JiraClient.create_jira_client')
    def test_create_ticket_calls_client_methods(self, mock, tmp_path):
        jira_client = MagicMock()
        response_mock = MagicMock()
        response_mock.json.return_value = {"key": "BUG-123"}
        jira_client.create_ticket.return_value = response_mock
        jira_client.get_ticket_fields.return_value = {}
        mock.return_value = jira_client

        with pytest.raises(SystemExit) as exit_result:
            cmd = JiraCreateTicket(folder_path=str(tmp_path), input_params=self.REQUIRED_INPUT_PARAMS)
            cmd.run()

        jira_client.create_ticket.assert_called_once()
        jira_client.get_ticket_fields.assert_called_once()
        assert exit_result.value.code == 0
