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


class SampleExecutionCommand(ExecutionCommand):

    def _validate(self):
        names = ["paths.input.params",
                 "paths.output.params",
                 "params.param_1",
                 "params.param_2"]
        return self.context.validate(names)

    def _execute(self):
        self.context.logger.info("Running SampleExecutionCommand - calculating sum of 'param_1' and 'param_2'...")
        result_sum = int(self.context.input_param_get("params.param_1")) + int(self.context.input_param_get("params.param_2"))
        self.context.output_param_set("params.result", result_sum)
        self.context.output_params_save()


class ExecutionCommandWithOptionalParams(ExecutionCommand):

    def _validate(self):
        names = ["paths.input.params", "paths.output.params"]
        return self.context.validate(names)

    def _execute(self):
        self.context.output_param_set("params.result", int(self.context.input_param_get("params.empty_param", 123)))
        self.context.output_params_save()


class TestExecCommandV1(unittest.TestCase):

    def test_cmd_execution_with_existing_context(self):
        with self.assertRaises(SystemExit) as exit_result:
            cmd = SampleExecutionCommand('./tests/data/generic-execution-command/valid/context.yaml')
            cmd.run()
        self.assertEqual(0, exit_result.exception.code)
        with open('./tests/data/generic-execution-command/valid/result.yaml', 'r', encoding='utf-8') as result_file:
            result = yaml.safe_load(result_file)
            self.assertEqual(19, int(result["params"]["result"]))

    def test_cmd_execution_with_invalid_params(self):
        with self.assertRaises(SystemExit) as exit_result:
            cmd = SampleExecutionCommand('./tests/data/generic-execution-command/invalid/context.yaml')
            cmd.run()
        self.assertEqual(1, exit_result.exception.code)

    def test_cmd_execution_with_empty_param_in_context(self):
        with self.assertRaises(SystemExit) as exit_result:
            cmd = ExecutionCommandWithOptionalParams('./tests/data/generic-execution-command/valid/context.yaml')
            cmd.run()
        self.assertEqual(0, exit_result.exception.code)
        with open('./tests/data/generic-execution-command/valid/result.yaml', 'r', encoding='utf-8') as result_file:
            result = yaml.safe_load(result_file)
            self.assertEqual(123, int(result["params"]["result"]))

if __name__ == '__main__':
    unittest.main()
