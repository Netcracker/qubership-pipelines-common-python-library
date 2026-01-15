from qubership_pipelines_common_library.v1.execution.exec_command import ExecutionCommand
from qubership_pipelines_common_library.v2.jira.enums.auth_type import AuthType
from qubership_pipelines_common_library.v2.jira.jira_utils import JiraUtils
from jira import Issue


class JiraCreateTicket(ExecutionCommand):

    RETRY_TIMEOUT_SECONDS = 180  # default value, how many seconds to try
    RETRY_WAIT_SECONDS = 1  # default value, how many seconds between tries
    DEFAULT_FIELD_NAMES_FILTER = [
        "fixVersions",
        "resolution",
        "priority",
        "labels",
        "versions",
        "assignee",
        "status",
        "components",
        "creator",
        "reporter",
        "issuetype",
        "project",
        "resolutiondate",
        "created",
        "updated",
        "description",
        "summary",
        "customfield_10014",
    ]

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

        self.ticket_fields = self.context.input_param_get("params.ticket.fields")
        self.project_key = self.ticket_fields.get('project', {}).get('key')
        self.issue_type_name = self.ticket_fields.get('issuetype', {}).get('name')

        if not self.project_key or not self.issue_type_name:
            self.context.logger.error("Can't find project.key and/or issuetype.name in input parameters")
            return False

        if not self._validate_mandatory_ticket_fields(self.ticket_fields):
            return False

        self.comment = self.context.input_param_get("params.ticket.comment")
        if field_names_filter := self.context.input_param_get("params.ticket.field_names_filter"):
            self.field_names_filter = [x.strip() for x in field_names_filter.split(",")]
        else:
            self.field_names_filter = self.DEFAULT_FIELD_NAMES_FILTER

        return True

    def _validate_mandatory_ticket_fields(self, ticket_fields):
        valid = True
        for field_key in ["project", "issuetype", "summary"]:
            if not field_key in ticket_fields:
                valid = False
                self.context.logger.error(f"Parameter '{field_key}' is mandatory but not found in ticket params map")
        return valid

    def _execute(self):
        # todo le: wrap create/comment in retry in utils?? (but dont retry auth errors)
        self.context.logger.info("Running jira-create-ticket")
        self.jira_client = JiraUtils.create_jira_client(
            self.jira_url, self.auth_type,
            self.jira_username, self.jira_password
        )

        self.context.logger.info(f"Creating ticket in project {self.project_key}, type {self.issue_type_name}")
        new_issue = self.jira_client.create_issue(fields=self.ticket_fields)
        self.ticket_key = new_issue.key
        self.context.logger.info(f"Ticket created successfully: {self.ticket_key}")

        if self.comment:
            try:
                self.jira_client.add_comment(self.ticket_key, self.comment)
                self.context.logger.info(f"Comment added to ticket {self.ticket_key}")
            except Exception as e:
                self._exit(False, f"Failed to add comment: {str(e)}")

        self.context.output_param_set("params.ticket.id", self.ticket_key)
        self.context.output_param_set("params.ticket.url", f"{self.jira_url}/browse/{self.ticket_key}")

        issue = self.jira_client.issue(self.ticket_key)
        filtered_response_fields = self._get_filtered_ticket_fields(issue, self.field_names_filter)
        self.context.output_param_set("params.ticket.fields", filtered_response_fields)

        self.context.output_params_save()
        self.context.logger.info("JIRA ticket creation completed successfully")

    def _get_filtered_ticket_fields(self, issue: Issue, field_names_filter: list[str]) -> dict:
        try:
            filtered_fields = {}
            for field_name in field_names_filter:
                if hasattr(issue.fields, field_name):
                    field_value = getattr(issue.fields, field_name)
                    if field_value is None:
                        filtered_fields[field_name] = None
                    elif isinstance(field_value, (str, int, float, bool)):
                        filtered_fields[field_name] = field_value
                    elif isinstance(field_value, list):
                        filtered_fields[field_name] = [
                            item.name if hasattr(item, 'name') else str(item)
                            for item in field_value
                        ]
                    elif hasattr(field_value, 'emailAddress'):
                        filtered_fields[field_name] = JiraUtils.serialize_person_ref(field_value)
                    elif hasattr(field_value, 'key'):
                        filtered_fields[field_name] = field_value.key
                    elif hasattr(field_value, 'name'):
                        filtered_fields[field_name] = field_value.name
                    elif hasattr(field_value, 'value'):
                        filtered_fields[field_name] = field_value.value
                    else:
                        filtered_fields[field_name] = str(field_value)

            return filtered_fields

        except Exception as e:
            self.context.logger.error(f"Failed to get filtered fields: {str(e)}")
            return {}
