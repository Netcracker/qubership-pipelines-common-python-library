from enum import StrEnum


class CliOutput:

    class OutputMode(StrEnum):
        OFF = 'OFF'
        INSECURE_PARAMS = 'INSECURE_PARAMS'
        SECURE_PARAMS = 'SECURE_PARAMS'
        MERGED_PARAMS = 'MERGED_PARAMS'

    class OutputFormat(StrEnum):
        YAML = 'YAML'
        JSON = 'JSON'
        PRETTY_JSON = 'PRETTY_JSON'

    OUTPUT_MODE = OutputMode.OFF
    OUTPUT_FORMAT = OutputFormat.YAML

    @staticmethod
    def configure(cli_output_mode: OutputMode, cli_output_format: OutputFormat):
        CliOutput.OUTPUT_MODE = cli_output_mode
        CliOutput.OUTPUT_FORMAT = cli_output_format

    @staticmethod
    def print_command_output(cmd):
        if CliOutput.OUTPUT_MODE == CliOutput.OutputMode.OFF:
            return
        output_data = CliOutput._get_output_data(cmd)
        output_text = CliOutput._get_output_text(output_data)
        print(output_text)

    @staticmethod
    def _get_output_data(cmd):
        if CliOutput.OUTPUT_MODE == CliOutput.OutputMode.INSECURE_PARAMS:
            output_data = cmd.context.output_params.content
        elif CliOutput.OUTPUT_MODE == CliOutput.OutputMode.SECURE_PARAMS:
            output_data = cmd.context.output_params_secure.content
        elif CliOutput.OUTPUT_MODE == CliOutput.OutputMode.MERGED_PARAMS:
            from qubership_pipelines_common_library.v1.utils.utils import recursive_merge
            output_data = recursive_merge(cmd.context.output_params.content, cmd.context.output_params_secure.content)
        else:
            raise Exception(f"Unsupported Output Mode - {CliOutput.OUTPUT_MODE}")
        return output_data

    @staticmethod
    def _get_output_text(output_data):
        if CliOutput.OUTPUT_FORMAT == CliOutput.OutputFormat.YAML:
            import yaml
            output_text = yaml.safe_dump(output_data, default_flow_style=False, sort_keys=False)
        elif CliOutput.OUTPUT_FORMAT == CliOutput.OutputFormat.JSON:
            import json
            output_text = json.dumps(output_data)
        elif CliOutput.OUTPUT_FORMAT == CliOutput.OutputFormat.PRETTY_JSON:
            import json
            output_text = json.dumps(output_data, indent=2)
        else:
            raise Exception(f"Unsupported Output Format - {CliOutput.OUTPUT_FORMAT}")
        return output_text
