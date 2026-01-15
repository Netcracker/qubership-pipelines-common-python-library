from qubership_pipelines_common_library.v1.execution.exec_command import ExecutionCommand


class JiraUtils:

    @staticmethod
    def add_ticket_comment(command: ExecutionCommand):
        try:
            command.context.logger.info(f"Adding comment to ticket {command.ticket_key}...")
            add_ticket_comment_response = command.jira_client.add_ticket_comment(
                command.ticket_key, command.ticket_comment,
                retry_timeout_seconds=command.retry_timeout_seconds,
                retry_wait_seconds=command.retry_wait_seconds
            )
            if not add_ticket_comment_response.ok:
                command._exit(False, f"Can't add ticket comment. Response status: {add_ticket_comment_response.status_code}")
            command.context.logger.info(f"Comment added to ticket {command.ticket_key}")
        except Exception as e:
            command._exit(False, f"Can't add ticket comment. Response exception: {str(e)}")
