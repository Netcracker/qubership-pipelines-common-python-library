import re

from qubership_pipelines_common_library.v1.execution.exec_command import ExecutionCommand
from qubership_pipelines_common_library.v2.jira.jira_client import JiraClient, AuthType
from qubership_pipelines_common_library.v2.jira.jira_utils import JiraUtils


class JiraUpdateTicket(ExecutionCommand):
    """
    Updates ticket fields and transitions status.

    Input Parameters Structure (this structure is expected inside "input_params.params" block):
    ```
    {
        "ticket": {
            "fields: {                                                # REQUIRED: Dict structure that will be used as ticket-update-body, without transformations
                "status": {"name": "Done"},                           # OPTIONAL: Next status name
                "transition": {"name": "From Review to Done"},        # OPTIONAL: Transition name
                "priority": {"name": "High"},                         # OPTIONAL: Other ticket fields with different formats, depending on your Project configuration
                "duedate": "2030-02-20",                              # OPTIONAL: Text-value fields need no dict wrappers
                "description": "Ticket body",
                "labels": ["Test_Label1"],
            },
            "id": "BUG-567",                                            # REQUIRED: Ticket ID
            "comment": "your comment body",                             # OPTIONAL: Comment to add to created ticket
            "field_names_filter": "summary,issuetype,creator,status",   # OPTIONAL: Comma-separated names of fields to extract from created ticket to output params
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

    Command name: "jira-update-ticket"
    """
    RETRY_TIMEOUT_SECONDS = 180  # default value, how many seconds to try
    RETRY_WAIT_SECONDS = 1  # default value, how many seconds between tries

    def _validate(self):
        names = [
            "paths.input.params",
            "paths.output.params",
            "systems.jira.url",
            "systems.jira.username",
            "systems.jira.password",
            "params.ticket.id",
            "params.ticket.fields",
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
        self.ticket_fields = self.context.input_param_get("params.ticket.fields")
        self.next_status_name = self.ticket_fields.pop('status', {}).get('name')
        self.transition_name = self.ticket_fields.pop('transition', {}).get('name')

        if field_names_filter := self.context.input_param_get("params.ticket.field_names_filter"):
            self.field_names_filter = [x.strip() for x in re.split(r'[,;]+', field_names_filter)]
        else:
            self.field_names_filter = JiraClient.DEFAULT_FIELD_NAMES_FILTER

        return True

    def _execute(self):
        self.context.logger.info("Running jira-update-ticket")
        self.context.logger.info(f"Updating ticket {self.ticket_key}...")
        self.jira_client = JiraClient.create_jira_client(
            self.jira_url, self.jira_username, self.jira_password, self.auth_type,
            self.retry_timeout_seconds, self.retry_wait_seconds,
        )

        editmeta_fields = self.jira_client.get_editmeta_fields(self.ticket_key)
        self.filtered_ticket_fields = JiraClient.filter_ticket_fields(self.ticket_fields, editmeta_fields)
        self.context.logger.debug(f"Filtered ticket fields: {self.filtered_ticket_fields}")

        update_ticket_response = self.jira_client.update_ticket(
            self.ticket_key, self.filtered_ticket_fields,
            retry_timeout_seconds=self.retry_timeout_seconds, retry_wait_seconds=self.retry_wait_seconds
        )
        if not update_ticket_response.ok:
            self._exit(False, f"Can't update ticket. Response status: {update_ticket_response.status_code}")

        if self.next_status_name:
            self.context.logger.info(f"Updating ticket status to '{self.next_status_name}'...")
            self._perform_status_transition()

        if self.ticket_comment:
            JiraUtils.add_ticket_comment(self)

        self.context.output_param_set("params.ticket.id", self.ticket_key)
        self.context.output_param_set("params.ticket.url", f"{self.jira_url}/browse/{self.ticket_key}")

        filtered_response_fields = self.jira_client.get_ticket_fields(self.ticket_key, self.field_names_filter)
        self.context.output_param_set("params.ticket.fields", filtered_response_fields)

        self.context.output_params_save()
        self.context.logger.info("Update ticket request executed. See output params for details")

    def _perform_status_transition(self):

        ticket_current_status = self.jira_client.get_ticket_fields(self.ticket_key, ["status"]).get("status", {}).get("name")
        if str(self.next_status_name).strip().lower() == str(ticket_current_status).strip().lower():
            self.context.logger.info(f"Ticket {self.ticket_key} already has '{self.next_status_name}' status. Skipping status transition.")

        else:
            transitions = self.jira_client.get_ticket_transitions(self.ticket_key)
            if not transitions:
                self._exit(False, f"Can't find ticket {self.ticket_key} transitions.")

            transition = self.jira_client.find_applicable_transition(
                transitions, self.next_status_name, self.transition_name
            )
            if transition is None:
                self._exit(False, f"Can't find transition with next status '{self.next_status_name}'.")

            ticket_transition_fields = JiraClient.filter_ticket_fields(self.ticket_fields, transition.get("fields"))
            transition_response = self.jira_client.perform_ticket_transition(
                self.ticket_key, transition.get("id"), ticket_transition_fields
            )
            if not transition_response.ok:
                self._exit(False, f"Can't perform ticket status transition. Response status: {transition_response.status_code}")
