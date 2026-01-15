from qubership_pipelines_common_library.v1.execution.exec_command import ExecutionCommand
from qubership_pipelines_common_library.v2.jira.jira_client import JiraClient, AuthType
from qubership_pipelines_common_library.v2.jira.jira_utils import JiraUtils


class JiraAddTicketComment(ExecutionCommand):
    """
    Adds comment to JIRA ticket and retrieves latest comments.

    Input Parameters Structure (this structure is expected inside "input_params.params" block):
    ```
    {
        "ticket": {
            "id": "BUG-567",                    # REQUIRED: Ticket ID
            "comment": "your comment body",     # REQUIRED: Comment body
            "latest_comments_count": 50,        # OPTIONAL: Number of latest comments to fetch
        },
        "retry_timeout_seconds": 180,           # OPTIONAL: Timeout for JIRA client operations in seconds (default: 180)
        "retry_wait_seconds": 1,                # OPTIONAL: Wait interval between retries in seconds (default: 1)
    }
    ```

    Systems Configuration (expected in "systems.jira" block):
    ```
    {
        "url": "https://your_cloud_jira.atlassian.net",         # REQUIRED: JIRA server URL
        "username": "your_username_or_email",                   # REQUIRED: JIRA user login or email
        "password": "<your_token>",                             # REQUIRED: JIRA user token
        "auth_type": "basic"                                    # OPTIONAL: 'basic' or 'bearer'
    }
    ```

    Command name: "jira-add-ticket-comment"
    """

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
        self.jira_client = JiraClient.create_jira_client(
            self.jira_url, self.jira_username, self.jira_password, self.auth_type,
            self.retry_timeout_seconds, self.retry_wait_seconds,
        )

        if self.ticket_comment:
            JiraUtils.add_ticket_comment(self)

        total_comments = 0
        parsed_latest_comments = []
        try:
            self.latest_comments = self.jira_client.get_latest_ticket_comments(self.ticket_key, max_results=self.latest_comments_count)
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
            "body": comment.get("body"),
            "created": comment.get("created"),
            "updated": comment.get("updated"),
            "author": JiraClient.serialize_person_ref(comment.get("author", {})),
            "updateAuthor": JiraClient.serialize_person_ref(comment.get("updateAuthor", {})),
        }
