import tempfile
import os
import traceback

from qubership_pipelines_common_library.v1.execution.exec_command import ExecutionCommand
from qubership_pipelines_common_library.v1.webex_client import WebexClient
from webexpythonsdk.exceptions import ApiError
from requests.exceptions import ProxyError


class SendWebexMessage(ExecutionCommand):
    """
    This command sends Webex message with optional attachments.

    Input Parameters Structure (this structure is expected inside "input_params.params" block):
    ```
    {
        "webex_message": "Hello, world!",           # REQUIRED: Text message (Markdown format is supported)
        "parent_id": "1234321",                     # OPTIONAL: The parent message to reply to
        "attachments": {                            # OPTIONAL: Dict with attachments
            "unique_attachment_key": {
                "name": "HTML_report.html",         # REQUIRED: File name used for attachment
                "content": "<html>...</html>",      # REQUIRED: Text content put inside attachment
                "mime_type": "text/html",
            },
            "another_attachment_key": {...}
        }
    }
    ```

    Systems Configuration (expected in "systems.webex" block):
    ```
    {
        "room_id": "...Y2lzY29zc...",               # REQUIRED: Webex unique room_id where message will be posted
        "token": "your_bot_account_token"           # REQUIRED: Bot/Service account token that will be used to send message
        "proxy": "https://127.0.0.1"                # OPTIONAL: Host to be used as a webex-proxy
    }
    ```

    Output Parameters:
        - params.message_id: Received `message_id` of sent message
        - params.attachment_message_ids: dict of `attachment_name` -> `message_id`

    Command name: "send-webex-message"
    """

    def _validate(self):
        required_params = [
            "paths.input.params",
            "paths.output.params",
            "systems.webex.room_id",
            "systems.webex.token",
            "params.webex_message",
        ]
        if not self.context.validate(required_params):
            return False

        self.webex_room_id = self.context.input_param_get("systems.webex.room_id")
        self.webex_token = self.context.input_param_get("systems.webex.token")
        self.webex_proxy = self.context.input_param_get("systems.webex.proxy")
        self.webex_message = self.context.input_param_get("params.webex_message")
        self.webex_parent_id = self.context.input_param_get("params.parent_id", "")

        self.attachments = []
        for key, data in self.context.input_param_get("params.attachments", {}).items():
            if not data.get("content") or not data.get("name"):
                self.context.logger.error(f"Attachment with key [{key}] is missing content and/or name!")
                return False
            self.attachments.append({
                "name": data.get("name"),
                "mime_type": data.get("mime_type"),
                "content": data.get("content")
            })

        self.webex_client = WebexClient(
            bot_token=self.webex_token,
            proxies={"https": self.webex_proxy} if self.webex_proxy else None
        )
        return True

    def _execute(self):
        try:
            response = self.webex_client.send_message(
                room_id=self.webex_room_id,
                parent_id=self.webex_parent_id,
                markdown=self.webex_message
            )
            message_id = response.id if response else None
            self.context.output_param_set("params.message_id", message_id)

            if self.attachments:
                attachment_message_ids = {}
                for attachment in self.attachments:
                    attachment_message_ids[attachment["name"]] = self._send_attachment(attachment)
                self.context.output_param_set("params.attachment_message_ids", attachment_message_ids)

            self.context.output_params_save()
            self.context.logger.info("Webex message sent successfully.")

        except ApiError as e:
            self.context.logger.debug("Full traceback: %s", traceback.format_exc())
            error_str = str(e)
            if "404" in error_str or "Not Found" in error_str:
                error_msg = f"Webex room not found - verify room_id '{self.webex_room_id}' exists. {error_str}"
            elif "401" in error_str or "Unauthorized" in error_str:
                error_msg = f"Webex authentication failed - verify token is valid: {error_str}"
            else:
                error_msg = f"Webex API error: {error_str}"
            self._exit(False, error_msg)

        except ProxyError as e:
            self.context.logger.debug("Full traceback: %s", traceback.format_exc())
            self._exit(False, f"Invalid proxy: {str(e)}")

        except Exception as e:
            self._exit(False, f"Failed to send Webex message: {e}\n{traceback.format_exc()}")

    def _send_attachment(self, attachment: dict):
        temp_dir = tempfile.gettempdir()
        temp_file_path = os.path.join(temp_dir, attachment["name"])
        with open(temp_file_path, "w") as temp_file:
            temp_file.write(attachment["content"])
            temp_file_path = temp_file.name
        try:
            attachment_response = self.webex_client.send_message(room_id=self.webex_room_id,
                                                                 parent_id=self.webex_parent_id,
                                                                 markdown=attachment["name"],
                                                                 attachment_path=temp_file_path)
            return attachment_response.id if attachment_response else None
        finally:
            os.remove(temp_file_path)
