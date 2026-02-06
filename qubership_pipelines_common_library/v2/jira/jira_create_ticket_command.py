import re

from qubership_pipelines_common_library.v1.execution.exec_command import ExecutionCommand
from qubership_pipelines_common_library.v2.jira.jira_client import JiraClient, AuthType
from qubership_pipelines_common_library.v2.jira.jira_utils import JiraUtils


class JiraCreateTicket(ExecutionCommand):
    """
    Creates new issue/ticket in JIRA project.

    Input Parameters Structure (this structure is expected inside "input_params.params" block):
    ```
    {
        "ticket": {
            "fields: {                                                  # REQUIRED: Dict structure that will be used as ticket-creation-body, without transformations
                "project": {"key": "<YOUR_PROJECT_KEY>"},               # REQUIRED: Project Key
                "issuetype": {"name": "Bug"},                           # REQUIRED: Issue type name
                "priority": {"name": "High"},                           # OPTIONAL: Other ticket fields with different formats, depending on your Project configuration
                "duedate": "2030-02-20",                                # OPTIONAL: Text-value fields need no dict wrappers
                "summary": "[SOME_LABEL] Ticket Subject",
                "description": "Ticket body",
                "components": [{"name":"COMPONENT NAME"}],
                "labels": ["Test_Label1"],
            },
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

    Command name: "jira-create-ticket"
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

        self.ticket_comment = self.context.input_param_get("params.ticket.comment")
        self.ticket_fields = self.context.input_param_get("params.ticket.fields", {})
        self.project_key = self.ticket_fields.get('project', {}).get('key')
        self.issue_type_name = self.ticket_fields.get('issuetype', {}).get('name')

        if not self.project_key or not self.issue_type_name:
            self.context.logger.error("Can't find project.key and/or issuetype.name in input parameters")
            return False

        if not self._validate_mandatory_ticket_fields(self.ticket_fields):
            return False

        if field_names_filter := self.context.input_param_get("params.ticket.field_names_filter"):
            self.field_names_filter = [x.strip() for x in re.split(r'[,;]+', field_names_filter)]
        else:
            self.field_names_filter = JiraClient.DEFAULT_FIELD_NAMES_FILTER

        return True

    def _validate_mandatory_ticket_fields(self, ticket_fields):
        valid = True
        for field_key in ["project", "issuetype", "summary"]:
            if field_key not in ticket_fields:
                valid = False
                self.context.logger.error(f"Parameter '{field_key}' is mandatory but not found in ticket params map")
        return valid

    def _execute(self):
        self.context.logger.info("Running jira-create-ticket")
        self.context.logger.info(f"Creating ticket in project {self.project_key}, type {self.issue_type_name}")
        self.jira_client = JiraClient.create_jira_client(
            self.jira_url, self.jira_username, self.jira_password, self.auth_type,
            self.retry_timeout_seconds, self.retry_wait_seconds,
        )

        createmeta_fields = self.jira_client.get_createmeta_fields(self.project_key, self.issue_type_name)
        self.filtered_ticket_fields = JiraClient.filter_ticket_fields(self.ticket_fields, createmeta_fields)
        self.context.logger.debug(f"Filtered ticket fields: {self.filtered_ticket_fields}")

        create_ticket_response = self.jira_client.create_ticket(self.filtered_ticket_fields,
                                                                retry_timeout_seconds=self.retry_timeout_seconds,
                                                                retry_wait_seconds=self.retry_wait_seconds)
        if not create_ticket_response.ok:
            self._exit(False, f"Can't create ticket. Response status: {create_ticket_response.status_code}")
        self.ticket_key = create_ticket_response.json().get('key')
        self.context.logger.info(f"Ticket created successfully: {self.ticket_key}")

        if self.ticket_comment:
            JiraUtils.add_ticket_comment(self)

        self.context.output_param_set("params.ticket.id", self.ticket_key)
        self.context.output_param_set("params.ticket.url", f"{self.jira_url}/browse/{self.ticket_key}")

        filtered_response_fields = self.jira_client.get_ticket_fields(self.ticket_key, self.field_names_filter)
        self.context.output_param_set("params.ticket.fields", filtered_response_fields)

        self.context.output_params_save()
        self.context.logger.info("JIRA ticket creation completed successfully")
