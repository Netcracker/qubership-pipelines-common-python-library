from qubership_pipelines_common_library.v1.execution.exec_command import ExecutionCommand
from qubership_pipelines_common_library.v2.jira.enums.auth_type import AuthType
from qubership_pipelines_common_library.v2.jira.jira_utils import JiraUtils


class JiraAddTicketComment(ExecutionCommand):

    RETRY_TIMEOUT_SECONDS = 180  # default value, how many seconds to try
    RETRY_WAIT_SECONDS = 1  # default value, how many seconds between tries
    LATEST_COMMENTS_COUNT = 50 # default value, max amount of comments in response

    def _validate(self):
        names = [
            "paths.input.params",
            "paths.output.params",
            "systems.jira.url",
            "systems.jira.username",
            "systems.jira.password",
            "params.ticket.id",
            "params.ticket.comment",
        ]
        if not self.context.validate(names):
            return False

        self.retry_timeout_seconds = int(self.context.input_param_get("params.retry_timeout_seconds", self.RETRY_TIMEOUT_SECONDS))
        self.retry_wait_seconds = int(self.context.input_param_get("params.retry_wait_seconds", self.RETRY_WAIT_SECONDS))

        self.jira_url = self.context.input_param_get("systems.jira.url").rstrip('/')
        self.jira_username = self.context.input_param_get("systems.jira.username")
        self.jira_password = self.context.input_param_get("systems.jira.password")
        self.auth_type = self.context.input_param_get("systems.jira.auth_type", AuthType.BASIC)

        self.ticket_key = self.context.input_param_get("params.ticket.id")
        self.ticket_comment = self.context.input_param_get("params.ticket.comment")
        self.latest_comments_count = int(self.context.input_param_get("params.ticket.latest_comments_count", self.LATEST_COMMENTS_COUNT))
        return True

    def _execute(self):
        self.context.logger.info("Running jira-add-ticket-comment")
        self.jira_client = JiraUtils.create_jira_client(
            self.jira_url, self.auth_type,
            self.jira_username, self.jira_password
        )

        try:
            self.context.logger.info(f"Adding comment to ticket {self.ticket_key}...")
            self.jira_client.add_comment(issue=self.ticket_key, body=self.ticket_comment)
        except Exception as e:
            self._exit(False, f"Can't add ticket comment. Response exception: {str(e)}")

        total_comments = 0
        parsed_latest_comments = []
        try:
            self.latest_comments = self.jira_client.comments(issue=self.ticket_key, max_results=self.latest_comments_count, order_by="-created")
            total_comments = len(self.latest_comments)
            parsed_latest_comments = [self._parse_comment(comment) for comment in self.latest_comments]
        except Exception as e:
            self.context.logger.warning(f"Can't get latest ticket comments. Response exception: {str(e)}")

        self.context.output_param_set("params.ticket.id", self.ticket_key)
        self.context.output_param_set("params.ticket.url", f"{self.jira_url}/browse/{self.ticket_key}")
        self.context.output_param_set("params.ticket.total_comments", total_comments)
        self.context.output_param_set("params.ticket.latest_comments", parsed_latest_comments)
        self.context.output_params_save()
        self.context.logger.info("Add ticket comment request executed. See output params for details")

    @staticmethod
    def _parse_comment(comment):
        return {
            "body": comment.body,
            "created": comment.created,
            "updated": comment.updated,
            "author": JiraUtils.serialize_person_ref(comment.author),
            "updateAuthor": JiraUtils.serialize_person_ref(comment.updateAuthor),
        }
