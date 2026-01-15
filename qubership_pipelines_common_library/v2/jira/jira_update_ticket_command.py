from qubership_pipelines_common_library.v1.execution.exec_command import ExecutionCommand
from qubership_pipelines_common_library.v2.jira.enums.auth_type import AuthType
from qubership_pipelines_common_library.v2.jira.jira_utils import JiraUtils


class JiraUpdateTicket(ExecutionCommand):

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

        self.retry_timeout_seconds = int(
            self.context.input_param_get("params.retry_timeout_seconds", self.RETRY_TIMEOUT_SECONDS))
        self.retry_wait_seconds = int(
            self.context.input_param_get("params.retry_wait_seconds", self.RETRY_WAIT_SECONDS))

        self.jira_url = self.context.input_param_get("systems.jira.url").rstrip('/')
        self.jira_username = self.context.input_param_get("systems.jira.username")
        self.jira_password = self.context.input_param_get("systems.jira.password")
        self.auth_type = self.context.input_param_get("systems.jira.auth_type", AuthType.BASIC)

        self.ticket_key = self.context.input_param_get("params.ticket.id")
        self.ticket_comment = self.context.input_param_get("params.ticket.comment")
        self.ticket_fields = self.context.input_param_get("params.ticket.fields")
        self.project_key = self.ticket_fields.get('project', {}).get('key')
        self.issue_type_name = self.ticket_fields.get('issuetype', {}).get('name')

        if not self.project_key or not self.issue_type_name:
            self.context.logger.error("Can't find project.key and/or issuetype.name in input parameters")
            return False

        if field_names_filter := self.context.input_param_get("params.ticket.field_names_filter"):
            self.field_names_filter = [x.strip() for x in field_names_filter.split(",")]
        else:
            self.field_names_filter = self.DEFAULT_FIELD_NAMES_FILTER # todo le: common utils?

        return True

    def _execute(self):
        self.context.logger.info("Running jira-update-ticket")
        self.jira_client = JiraUtils.create_jira_client(
            self.jira_url, self.auth_type,
            self.jira_username, self.jira_password
        )

        # todo le: use jira lib client
        next_status_name = ""
        if "status" in ticket_fields:
            if "name" in ticket_fields["status"]:
                next_status_name = ticket_fields["status"]["name"]
            ticket_fields.pop("status")

        transition_name = ""
        if "transition" in ticket_fields:
            if "name" in ticket_fields["transition"]:
                transition_name = ticket_fields["transition"]["name"]
            ticket_fields.pop("transition")

        ticket_editmeta_fields = jira_client.get_ticket_editmeta_fields(ticket_id)
        filtered_fields = JiraUtils.filter_ticket_fields(ticket_fields, ticket_editmeta_fields)
        update_ticket_response = jira_client.update_ticket(ticket_id, filtered_fields,
                                                           retry_timeout_seconds=retry_timeout_seconds,
                                                           retry_wait_seconds=retry_wait_seconds)
        if not update_ticket_response.ok:
            self._exit(False, f"Can't update ticket. Response status: {update_ticket_response.status_code}")

        if next_status_name:
            ticket_current_status = jira_client.get_ticket_fields(ticket_id, "status")
            if str(next_status_name).strip().lower() == str(ticket_current_status["status"]["name"]).strip().lower():
                self.context.logger.info(f"Ticket {ticket_id} already has {next_status_name} status. Skipping update")
            else:
                transitions = jira_client.get_ticket_transitions(ticket_id)
                if not transitions:
                    self._exit(False, f"Can't find ticket {ticket_id} transitions.")
                transition = jira_client.find_transition_by_next_status_and_transition_name(transitions, next_status_name, transition_name)
                if transition is None:
                    self._exit(False, f"Can't find transition with next status {next_status_name}.")
                ticket_transition_fields = JiraUtils.filter_ticket_fields(ticket_fields, transition["fields"])
                perform_ticket_transition_response = jira_client.perform_ticket_transition(
                    ticket_id, transition['id'], ticket_transition_fields)
                if not perform_ticket_transition_response.ok:
                    self._exit(False,
                            f"Can't perform ticket {ticket_id} transition into status '{next_status_name}'. "
                            f"Response status: {perform_ticket_transition_response.status_code}")

        if self.ticket_comment:
            try:
                self.jira_client.add_comment(self.ticket_key, self.ticket_comment)
                self.context.logger.info(f"Comment added to ticket {self.ticket_key}")
            except Exception as e:
                self._exit(False, f"Failed to add comment: {str(e)}")


        self.context.output_param_set("params.ticket.id", self.ticket_key)
        self.context.output_param_set("params.ticket.url", f"{self.jira_url}/browse/{self.ticket_key}")

        issue = self.jira_client.issue(self.ticket_key)
        filtered_response_fields = self._get_filtered_ticket_fields(issue, self.field_names_filter) # todo le: utils
        self.context.output_param_set("params.ticket.fields", filtered_response_fields)

        self.context.output_params_save()
        self.context.logger.info("Update ticket request executed. See output params for details")
