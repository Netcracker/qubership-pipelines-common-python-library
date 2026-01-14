import smtplib
import socket
import ssl

from email.utils import formatdate
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from qubership_pipelines_common_library.v1.execution.exec_command import ExecutionCommand
from qubership_pipelines_common_library.v1.utils.utils_string import UtilsString


class SendEmail(ExecutionCommand):
    """
    This command sends email notification with optional attachments.

    Input Parameters Structure (this structure is expected inside "input_params.params" block):
    ```
    {
        "email_subject": "Report for 01.01.2026",                         # REQUIRED: E-mail subject
        "email_body": "Following jobs were completed: ...",               # REQUIRED: E-mail message
        "email_recipients": "user1@qubership.org,user2@qubership.org",    # REQUIRED: Comma-separated list of recipients
        "email_body_type": "plain",                                       # OPTIONAL: Either "plain" or "html
        "attachments": {                                                  # OPTIONAL: Dict with attachments
            "unique_attachment_key": {
                "name": "HTML_report.html",                               # REQUIRED: File name used for attachment
                "content": "<html>...</html>",                            # REQUIRED: Text content put inside attachment
                "mime_type": "text/html",
            },
            "another_attachment_key": {...}
        }
    }
    ```

    Systems Configuration (expected in "systems.email" block):
    ```
    {
        "server": "your.mail.server.org",           # REQUIRED: E-mail host server
        "port": "3025"                              # REQUIRED: E-mail port
        "user": "your@email.bot"                    # REQUIRED: E-mail user
        "password": "<email_password>"              # OPTIONAL: E-mail password
        "use_ssl": "False"                          # OPTIONAL: SMTP connection will use SSL mode (default: False)
        "use_tls": "False"                          # OPTIONAL: SMTP connection will use TLS mode (default: False)
        "verify": "False"                           # OPTIONAL: SSL Certificate verification (default: False)
        "timeout_seconds": "60"                     # OPTIONAL: SMTP connection timeout in seconds (default: 60)
    }
    ```

    Command name: "send-email"
    """

    EMAIL_BODY_TYPE_PLAIN = "plain"
    EMAIL_BODY_TYPE_HTML = "html"
    EMAIL_BODY_TYPES = [EMAIL_BODY_TYPE_PLAIN, EMAIL_BODY_TYPE_HTML]
    WAIT_TIMEOUT = 60

    def _validate(self):
        required_params = [
            "paths.input.params",
            "systems.email.server",
            "systems.email.port",
            "systems.email.user",
            "params.email_subject",
            "params.email_body",
            "params.email_recipients",
        ]
        if not self.context.validate(required_params):
            return False

        self.email_server = self.context.input_param_get("systems.email.server")
        self.email_port = self.context.input_param_get("systems.email.port")
        self.email_user = self.context.input_param_get("systems.email.user")
        self.email_password = self.context.input_param_get("systems.email.password")
        self.email_password = self.context.input_param_get("systems.email.password")
        self.timeout_seconds = max(1, int(self.context.input_param_get("systems.email.timeout_seconds", self.WAIT_TIMEOUT)))
        self.use_ssl = UtilsString.convert_to_bool(self.context.input_param_get("systems.email.use_ssl", False))
        self.use_tls = UtilsString.convert_to_bool(self.context.input_param_get("systems.email.use_tls", False))
        self.verify = UtilsString.convert_to_bool(self.context.input_param_get("systems.email.verify", False))

        self.email_subject = self.context.input_param_get("params.email_subject")
        self.email_body = self.context.input_param_get("params.email_body")
        self.email_recipients = [x.strip() for x in self.context.input_param_get("params.email_recipients").split(",")]

        self.email_body_type = self.context.input_param_get("params.email_body_type", SendEmail.EMAIL_BODY_TYPE_PLAIN)
        if self.email_body_type not in SendEmail.EMAIL_BODY_TYPES:
            self.context.logger.error(f"Incorrect email_body_type value: {self.email_body_type}. Only '{SendEmail.EMAIL_BODY_TYPES}' are supported")
            return False

        self.attachments = []
        for key, data in self.context.input_param_get("params.attachments", {}).items():
            if not data.get("content") or not data.get("name"):
                self.context.logger.error(f"Attachment with key [{key}] is missing content and/or name!")
                return False
            self.attachments.append({
                "name": data.get("name"),
                "mime_type": data.get("mime_type", "text/plain"),
                "content": data.get("content")
            })

        return True

    def _execute(self):
        try:
            msg = MIMEMultipart()
            msg["From"] = self.email_user
            msg["To"] = ", ".join(self.email_recipients)
            msg["Subject"] = self.email_subject
            msg["Date"] = formatdate(localtime=True)
            msg.attach(MIMEText(self.email_body, self.email_body_type))

            if self.attachments:
                for attachment in self.attachments:
                    part = MIMEText(attachment["content"], attachment["mime_type"])
                    part.add_header('Content-Disposition', f'attachment; filename="{attachment["name"]}"')
                    msg.attach(part)

            self.context.logger.debug(f"Connecting to SMTP server: {self.email_server}:{self.email_port}"
                                      f", using SSL: {self.use_ssl}, TLS: {self.use_tls}, verify: {self.verify}")
            ssl_context = ssl.create_default_context() if self.verify else ssl._create_unverified_context()
            if self.use_ssl:
                smtp = smtplib.SMTP_SSL(self.email_server, self.email_port, timeout=self.timeout_seconds, context=ssl_context)
            else:
                smtp = smtplib.SMTP(self.email_server, self.email_port, timeout=self.timeout_seconds)

            try:
                if self.use_tls and not self.use_ssl:
                    smtp.starttls(context=ssl_context)

                if self.email_password:
                    self.context.logger.debug("Authenticating with server...")
                    smtp.login(self.email_user, self.email_password)

                self.context.logger.debug("Sending email...")
                smtp.send_message(msg)
                self.context.logger.info(f"Email sent successfully to {len(self.email_recipients)} recipients: {self.email_recipients}")
            finally:
                try:
                    smtp.quit()
                except Exception:
                    pass

        except socket.gaierror as e:
            self._exit(False, f"Invalid SMTP server. Cannot resolve hostname '{self.email_server}': {str(e)}")
        except socket.timeout as e:
            self._exit(False, f"Connection timeout to SMTP server: {str(e)}")
        except smtplib.SMTPAuthenticationError as e:
            self._exit(False, f"SMTP authentication failed: {str(e)}")
        except smtplib.SMTPRecipientsRefused as e:
            self._exit(False, f"Email recipients rejected - verify email addresses are valid and domain exists: {str(e)}. SMTP may reject domains like: @gmail.com and etc.")
        except Exception as e:
            self._exit(False, f"Failed to send email: {str(e)}")
