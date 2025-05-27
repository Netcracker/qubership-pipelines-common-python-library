# Copyright 2025 NetCracker Technology Corporation
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
from qubership_pipelines_common_library.v1.execution.exec_command import ExecutionCommand


class SampleNoContextCommand(ExecutionCommand):

    def _validate(self):
        names = ["paths.input.params",
                 "paths.output.params",
                 "params.test_secure_param",
                 "systems.test_system.test_password"
                 ]
        return self.context.validate(names)

    def _execute(self):
        self.context.logger.info("Running SampleNoContextCommand - checking if all expected params are present")
        if self.context.input_param_get("systems.test_system.test_password") != "expected_secure_password":
            raise Exception("Not the expected password!")
        if self.context.input_param_get("params.test_secure_param") != "expected_secure_parameter":
            raise Exception("Not the expected secure parameter!")
        self.context.output_param_set("params.result", "OK")
        self.context.output_params_save()


class TestNoContextExecutionCommand(unittest.TestCase):

    def test_umbrella_command_creates_context(self):
        with self.assertRaises(SystemExit) as exit_result:
            cmd = SampleNoContextCommand(input_params_secure={
                "params": {
                    "test_secure_param": "expected_secure_parameter",
                },
                "systems": {
                    "test_system": {
                        "test_password": "expected_secure_password"
                    },
                }
            })
            cmd.run()
        self.assertEqual(0, exit_result.exception.code)


if __name__ == '__main__':
    unittest.main()
