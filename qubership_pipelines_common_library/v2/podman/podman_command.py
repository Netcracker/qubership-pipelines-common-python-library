import os, subprocess, time, uuid

from pathlib import Path
from qubership_pipelines_common_library.v1.execution.exec_command import ExecutionCommand
from qubership_pipelines_common_library.v1.utils.utils_string import UtilsString


class PodmanRunImage(ExecutionCommand):
    """
        Executes a container using "podman run" command.

        This command supports running containers with configurable execution parameters,
        environment variable management, file mounting, and output extraction.

        Input Parameters Structure (this structure is expected inside "input_params.params" block):
        ```
        {
            "image": "docker.io/library/hello-world:latest",  # REQUIRED: Container image to run
            "command": "python -m pipelines_declarative_executor run --pipeline_dir=\"/WORK/EXEC_DIR\"",  # OPTIONAL: Command to execute in container
            "execution_config": { # ALL OF THESE ARE OPTIONAL
                "working_dir": "/some/dir/inside/container",  # Working directory inside container
                "timeout": "600",  # Maximum execution time in seconds
                "operations_timeout": "15",  # Timeout for operations like file copying
                "remove_container": True,  # Whether to remove container after execution
                "save_stdout_to_logs": True,  # Save container stdout to execution logs
                "save_stdout_to_files": True,  # Save container stdout to output files
                "save_stdout_to_params": False,  # Save container stdout to output parameters
                "expected_return_codes": "0,125",  # Comma-separated list of acceptable exit codes
                "additional_run_flags": "--cgroups=disabled",  # Optional string of flags that will be added to "podman run" command
            },
            "before_script": {
                "mounts": {  # Filesystem mounts, "host_path: container_path"
                    "output_files": "/WORK",
                    "prepared_data": "/CONFIGS"
                },
                "env_vars": {
                    "explicit": {  # Direct environment variable assignment
                        "PIPELINES_DECLARATIVE_EXECUTOR_ENCRYPT_OUTPUT_SECURE_PARAMS": False
                    },
                    "env_files": [  # Environment files on host to load and pass into container
                        "../CONFIGS/sample.env"
                    ],
                    "pass_via_file": {  # Sensitive vars passed via temp file
                        "SOMETHING_VERY_SECURE": "PASSWORD"
                    },
                    "host_prefixes": [  # Host environment variable prefixes to pass through. Can use "*" to pass everything from host.
                        "SOME_PREFIX_*"
                    ]
                }
            },
            "after_script": {
                "copy_files_to_host": {  # Copy files from container to host after execution, "host_path: container_path"
                    "output_files/report.json": "/WORK/EXEC_DIR/pipeline_state/pipeline_ui_view.json",
                    "output_files/pipeline_state": "/WORK/EXEC_DIR/pipeline_state",
                },
                "extract_params_from_files": {  # OPTIONAL: Extract parameters from container files. Supports JSON, YAML, and ENV files
                    "SOME_FILE_IN_CONTAINER": "SECTION_NAME_IN_PARAMS_WHERE_IT_WILL_BE_STORED",
                }
            }
        }
        ```

        Output Parameters:
            - params.execution_time: Total execution time in seconds
            - params.return_code: Container exit code
            - params.stdout: Container stdout (if save_stdout_to_params enabled)
            - params.stderr: Container stderr (if save_stdout_to_params enabled)
            - params.extracted_output.*: Extracted parameters from files (if extract_params_from_files configured)

        Notes:
            - The command automatically handles container lifecycle including start, execution, and cleanup
            - All host-paths (including mount paths) are resolved relative to context directory.
        """

    def _validate(self):
        names = [
            "paths.input.params",
            "paths.output.params",
            "paths.output.files",
            "params.image",
        ]
        if not self.context.validate(names):
            return False

        # Check if podman is available
        try:
            subprocess.run(["podman", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.context.logger.error("Podman is not available on this system. Please install podman to use this command.")
            return False

        # Setup defaults & convert values
        self.image = self.context.input_param_get("params.image")
        self.command = self.context.input_param_get("params.command")

        # execution_config
        self.working_dir = self.context.input_param_get("params.execution_config.working_dir")
        self.timeout = float(self.context.input_param_get("params.execution_config.timeout", 60))
        self.operations_timeout = float(self.context.input_param_get("params.execution_config.operations_timeout", 15))
        self.remove_container = UtilsString.convert_to_bool(self.context.input_param_get("params.execution_config.remove_container", True))
        self.save_stdout_to_logs = UtilsString.convert_to_bool(self.context.input_param_get("params.execution_config.save_stdout_to_logs", True))
        self.save_stdout_to_files = UtilsString.convert_to_bool(self.context.input_param_get("params.execution_config.save_stdout_to_files", True))
        self.save_stdout_to_params = UtilsString.convert_to_bool(self.context.input_param_get("params.execution_config.save_stdout_to_params", False))
        self.expected_return_codes = [int(num) for num in self.context.input_param_get("params.execution_config.expected_return_codes", "0").split(',')]
        self.additional_run_flags = self.context.input_param_get("params.execution_config.additional_run_flags")

        # before_script
        self.mounts_config = self.context.input_param_get("params.before_script.mounts", {})
        self.env_vars_config = self.context.input_param_get("params.before_script.env_vars", {})

        # after_script
        self.copy_files_config = self.context.input_param_get("params.after_script.copy_files_to_host", {})
        self.extract_params_config = self.context.input_param_get("params.after_script.extract_params_from_files", {})

        # Get base paths
        self.context_dir_path = Path(os.path.dirname(self.context.context_path))
        self.input_params_path = Path(self.context.input_param_get("paths.input.params"))
        self.output_params_path = Path(self.context.input_param_get("paths.output.params"))
        self.output_files_path = Path(self.context.input_param_get("paths.output.files"))
        self.container_name = f"podman_{str(uuid.uuid4())}"
        return True

    def _run_sp_command(self, command, timeout=None):
        return subprocess.run(command, capture_output=True, text=True,
                              timeout=timeout if timeout else self.timeout,
                              cwd=self.context_dir_path)

    def _build_podman_command(self) -> list[str]:
        cmd = ["podman", "run", "--name", self.container_name]

        if self.additional_run_flags:
            import shlex
            cmd.extend(shlex.split(self.additional_run_flags))

        if self.working_dir:
            cmd.extend(["--workdir", self.working_dir])

        if self.env_vars_config:
            cmd.extend(self._build_command_env_var_args())

        for host_path, container_path in self.mounts_config.items():
            cmd.extend(["--mount", f"type=bind,source={host_path},target={container_path}"])

        cmd.append(self.image)

        if self.command:
            import shlex
            cmd.extend(shlex.split(self.command))

        return cmd

    def _build_command_env_var_args(self) -> list[str]:
        args = []
        for key, value in self.env_vars_config.get("explicit", {}).items():
            args.extend(["--env", f"{key}={value}"])

        for prefix in self.env_vars_config.get("host_prefixes", []):
            args.extend(["--env", f"{prefix}"])

        for env_file in self.env_vars_config.get("env_files", []):
            args.extend(["--env-file", f"{env_file}"])

        if self.env_vars_config.get("pass_via_file"):
            env_file_path = self.context_dir_path.joinpath("temp").joinpath("temp.env")
            env_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(env_file_path, 'w') as f:
                for key, value in self.env_vars_config["pass_via_file"].items():
                    f.write(f"{key}={value}\n")
            args.extend(["--env-file", str(env_file_path)])

        return args

    def _copy_files_from_container(self):
        for host_path, container_path in self.copy_files_config.items():
            full_host_path = self.context_dir_path.joinpath(host_path)
            full_host_path.parent.mkdir(parents=True, exist_ok=True)

            copy_command = ["podman", "cp", f"{self.container_name}:{container_path}", str(full_host_path)]
            try:
                copy_result = self._run_sp_command(copy_command, self.operations_timeout)
                if copy_result.returncode != 0:
                    self.context.logger.warning(f"Failed to copy {container_path} to {host_path}: {copy_result.stderr}")
                else:
                    self.context.logger.debug(f"Copied {container_path} to {host_path}")
            except subprocess.TimeoutExpired:
                self.context.logger.warning(f"Copy command timed out after {self.operations_timeout} seconds")

    def _extract_params_from_container(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            for container_file_path, output_key_base in self.extract_params_config.items():
                try:
                    temp_file_path = Path(temp_dir) / Path(container_file_path).name
                    copy_command = ["podman", "cp", f"{self.container_name}:{container_file_path}", str(temp_file_path)]
                    copy_result = self._run_sp_command(copy_command, self.operations_timeout)
                    if copy_result.returncode != 0:
                        self.context.logger.warning(f"Failed to copy file {container_file_path} for params-extraction: {copy_result.stderr}")
                        continue
                    if not temp_file_path.exists():
                        self.context.logger.warning(f"File {container_file_path} for params-extraction not found after copy")
                        continue
                    if file_content := self._parse_custom_file_params(temp_file_path):
                        base_key = output_key_base if output_key_base else container_file_path.replace('/','_').replace('.', '_')
                        self.context.output_param_set(f"params.extracted_output.{base_key}", file_content)
                except Exception as e:
                    self.context.logger.warning(f"Failed to extract params from file {container_file_path}: {e}")

    def _parse_custom_file_params(self, file_path: Path):
        try:
            try:
                import json
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass

            try:
                import yaml
                with open(file_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f)
            except Exception:
                pass

            try:
                key_values = {}
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            key_values[key.strip()] = value.strip()
                return key_values if key_values else None
            except Exception:
                pass

            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read().strip()

        except Exception as e:
            self.context.logger.warning(f"Failed to parse custom-params file {file_path}: {e}")
            return None

    def _write_stdout_files(self, stdout: str, stderr: str):
        (self.output_files_path / "container_stdout.txt").write_text(stdout, encoding='utf-8')
        (self.output_files_path / "container_stderr.txt").write_text(stderr, encoding='utf-8')

    def _process_output(self, output: subprocess.CompletedProcess):
        self.context.output_param_set("params.execution_time", f"{self.execution_time:0.3f}s")
        self.context.output_param_set("params.return_code", output.returncode)

        if output.stdout and isinstance(output.stdout, bytes):
            output.stdout = output.stdout.decode('utf-8', errors='replace')
        if output.stderr and isinstance(output.stderr, bytes):
            output.stderr = output.stderr.decode('utf-8', errors='replace')

        if self.save_stdout_to_logs:
            if output.stdout:
                self.context.logger.debug(f"Container stdout:\n{output.stdout}")
            if output.stderr:
                self.context.logger.debug(f"Container stderr:\n{output.stderr}")

        if self.save_stdout_to_files:
            self._write_stdout_files(output.stdout, output.stderr)

        if self.save_stdout_to_params:
            self.context.output_param_set("params.stdout", output.stdout)
            self.context.output_param_set("params.stderr", output.stderr)

        if self.extract_params_config:
            self._extract_params_from_container()

        if self.copy_files_config:
            self._copy_files_from_container()

        if output.returncode not in self.expected_return_codes:
            raise PodmanException(output.stderr)

    def _execute(self):
        self.context.logger.info(f"Running podman image \"{self.image}\"...")
        start = time.perf_counter()
        try:
            output = self._run_sp_command(self._build_podman_command())
            self.execution_time = time.perf_counter() - start
            self.context.logger.info(
                f"Container finished with code: {output.returncode}"
                f"\nExecution time: {self.execution_time:0.3f}s"
            )
            self._process_output(output)

        except subprocess.TimeoutExpired:
            self.context.logger.error(f"Container execution timed out after {self.timeout} seconds")
            raise

        except PodmanException:
            self.context.logger.error("Container exited with unexpected exitcode")
            raise

        except Exception as e:
            self.context.logger.error(f"Container execution failed: {e}")
            raise

        finally:
            if self.remove_container:
                remove_output = subprocess.run(["podman", "rm", "-f", self.container_name], capture_output=True)
                if remove_output.returncode != 0:
                    self.context.logger.warning(f"Failed to remove container {self.container_name}:\n{remove_output.stdout}\n{remove_output.stderr}")
            self.context.output_params_save()


class PodmanException(Exception):
    pass
