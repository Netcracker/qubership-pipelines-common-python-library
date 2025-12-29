import pytest
import yaml

from qubership_pipelines_common_library.v1.execution.exec_command import ExecutionCommand, ExecutionCommandExtension


class SampleExtendableCommand(ExecutionCommand):
    def _validate(self):
        names = ["paths.input.params",
                 "paths.output.params",
                 "params.param_1",
                 "params.param_2"]
        self.param_1 = int(self.context.input_param_get("params.param_1"))
        self.param_2 = int(self.context.input_param_get("params.param_2"))
        return self.context.validate(names)

    def _execute(self):
        self.context.logger.info("Running SampleExtendableCommand...")
        result_sum = self.param_1 + self.param_2
        self.context.output_param_set("params.result", result_sum)
        self.context.output_params_save()


class OverrideParam1PreExt(ExecutionCommandExtension):
    def execute(self):
        self.command.param_1 += 10


class OverrideResultPostExt(ExecutionCommandExtension):
    def execute(self):
        self.context.output_param_set("params.result", 12345)
        self.context.output_params_save()


class TestExtendableCommand:

    INPUT_PARAMS = {
        "params": {
            "param_1": "5",
            "param_2": "6",
        }
    }

    @staticmethod
    def _extract_result(path):
        with open(path / "output" / "params.yaml", 'r', encoding='utf-8') as result_file:
            return yaml.safe_load(result_file)

    def test_extendable_command_no_extensions(self, tmp_path):
        with pytest.raises(SystemExit) as exit_result:
            cmd = SampleExtendableCommand(folder_path=str(tmp_path), input_params=self.INPUT_PARAMS)
            cmd.run()
        assert exit_result.value.code == 0
        assert 11 == int(self._extract_result(tmp_path)["params"]["result"])

    def test_extendable_command_inject_pre_extension(self, tmp_path):
        with pytest.raises(SystemExit):
            cmd = SampleExtendableCommand(folder_path=str(tmp_path), input_params=self.INPUT_PARAMS,
                                          pre_execute_actions=[OverrideParam1PreExt()])
            cmd.run()
        assert 21 == int(self._extract_result(tmp_path)["params"]["result"])

    def test_extendable_command_inject_post_extension(self, tmp_path):
        with pytest.raises(SystemExit):
            cmd = SampleExtendableCommand(folder_path=str(tmp_path), input_params=self.INPUT_PARAMS,
                                          post_execute_actions=[OverrideResultPostExt()])
            cmd.run()
        assert 12345 == int(self._extract_result(tmp_path)["params"]["result"])

    def test_extendable_command_inject_multiple_pre_extensions(self, tmp_path):
        with pytest.raises(SystemExit):
            cmd = SampleExtendableCommand(folder_path=str(tmp_path), input_params=self.INPUT_PARAMS,
                                          pre_execute_actions=[OverrideParam1PreExt(),
                                                               OverrideParam1PreExt(),
                                                               OverrideParam1PreExt()])
            cmd.run()
        assert 41 == int(self._extract_result(tmp_path)["params"]["result"])
