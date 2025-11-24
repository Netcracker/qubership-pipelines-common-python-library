# Copyright 2024 NetCracker Technology Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest
import yaml

from qubership_pipelines_common_library.v1.execution.exec_command import ExecutionCommand


class SampleUmbrellaCommand(ExecutionCommand):

    def _validate(self):
        names = ["paths.output.params"]
        return self.context.validate(names)

    def _execute(self):
        sum_cmd1 = SumIntegersCommand(input_params={
            "params": {
                "param_1": 9,
                "param_2": 10,
            }
        })
        try:
            sum_cmd1.run()
        except SystemExit as e:
            self.context.logger.info(f"first cmd exited with code={e}")

        sum_cmd2 = SumIntegersCommand(input_params={
            "params": {
                "param_1": sum_cmd1.context.output_params.get("params.result"),
                "param_2": 1,
            }
        })
        try:
            sum_cmd2.run()
        except SystemExit as e:
            self.context.logger.info(f"first cmd exited with code={e}")

        self.context.output_param_set("params.result", sum_cmd2.context.output_params.get("params.result"))
        self.context.output_params_save()


class SumIntegersCommand(ExecutionCommand):

    def _validate(self):
        names = ["paths.input.params",
                 "paths.output.params",
                 "params.param_1",
                 "params.param_2"]
        return self.context.validate(names)

    def _execute(self):
        self.context.logger.info("Running SumIntegersCommand - calculating sum of 'param_1' and 'param_2'...")
        result_sum = int(self.context.input_param_get("params.param_1")) + int(self.context.input_param_get("params.param_2"))
        self.context.output_param_set("params.result", result_sum)
        self.context.output_params_save()


class TestUmbrellaExecutionCommand(unittest.TestCase):

    def test_umbrella_command_creates_context(self):
        with self.assertRaises(SystemExit) as exit_result:
            cmd = SampleUmbrellaCommand()
            cmd.run()
        self.assertEqual(0, exit_result.exception.code)
        with open(cmd.context.input_param_get("paths.output.params"), 'r', encoding='utf-8') as result_file:
            result = yaml.safe_load(result_file)
            self.assertEqual(20, int(result["params"]["result"]))


if __name__ == '__main__':
    unittest.main()
