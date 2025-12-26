# Podman Run Image Command

Executes a container using `podman run` command.

This command supports running containers with configurable execution parameters, environment variable management, file mounting, and output extraction.

## Input Parameters

This structure is expected inside the `input_params.params` block:

```json
{
    "image": "docker.io/library/hello-world:latest",
    "command": "python -m pipelines_declarative_executor run --pipeline_dir=\"/WORK/EXEC_DIR\"",
    "execution_config": {
        "working_dir": "/some/dir/inside/container",
        "timeout": "600",
        "operations_timeout": "15",
        "remove_container": true,
        "save_stdout_to_logs": true,
        "save_stdout_to_files": true,
        "save_stdout_to_params": false,
        "expected_return_codes": "0,125",
        "additional_run_flags": "--cgroups=disabled"
    },
    "before_script": {
        "mounts": {
            "output_files": "/WORK",
            "prepared_data": "/CONFIGS"
        },
        "env_vars": {
            "explicit": {
                "PIPELINES_DECLARATIVE_EXECUTOR_ENCRYPT_OUTPUT_SECURE_PARAMS": false
            },
            "env_files": [
                "../CONFIGS/sample.env"
            ],
            "pass_via_file": {
                "SOMETHING_VERY_SECURE": "PASSWORD"
            },
            "host_prefixes": [
                "SOME_PREFIX_*"
            ]
        }
    },
    "after_script": {
        "copy_files_to_host": {
            "output_files/report.json": "/WORK/EXEC_DIR/pipeline_state/pipeline_ui_view.json",
            "output_files/pipeline_state": "/WORK/EXEC_DIR/pipeline_state"
        },
        "extract_params_from_files": {
            "SOME_FILE_IN_CONTAINER": "SECTION_NAME_IN_PARAMS_WHERE_IT_WILL_BE_STORED"
        }
    }
}
```

## Parameter Reference

All params are referenced here without their top-level "params" section.

Actual `input_params.yaml` should look like this sample:

```yaml
kind: AtlasModuleParamsInsecure
apiVersion: v1
params:
  image: docker.io/library/hello-world:latest
  command: ....
  execution_config:
    timeout: 300
    save_container_stdout_to_params: True
  before_script:
    mounts:
      output_files: /WORK
```

Or you can also pass required parameters via CLI arguments:

`qubership_cli_samples podman-run -p params.image=docker.io/my_image -p params.execution_config.timeout=300`

### Required Parameters

- **`image`** (string): Container image to run

### Optional Parameters

#### Execution Configuration

- **`command`** (string): Command to execute in container
- **`execution_config`** (object): Container execution settings
  - **`working_dir`** (string): Working directory inside container
  - **`timeout`** (float/string): Maximum execution time in seconds (e.g. "60", "36.6", etc.)
  - **`operations_timeout`** (float/string): Timeout for operations like file copying in seconds
  - **`remove_container`** (boolean): Whether to remove container after execution
  - **`save_stdout_to_logs`** (boolean): Save container stdout to execution logs
  - **`save_stdout_to_files`** (boolean): Save container stdout to output files
  - **`save_stdout_to_params`** (boolean): Save container stdout to output parameters
  - **`expected_return_codes`** (string): Comma-separated list of acceptable exit codes
  - **`additional_run_flags`** (string): Flags that will be added to "podman run" command

#### Before Script Configuration

- **`before_script`** (object): Pre-execution configuration
  - **`mounts`** (object): Filesystem mounts from host to container (`host_path: container_path`)
  - **`env_vars`** (object): Environment variable configuration. There's podman-specific priority of these vars (lower to highest): file vars, direct vars, host vars.
    - **`explicit`** (object): Direct environment variable assignment
    - **`env_files`** (array): Environment files on host to load and pass into container
    - **`pass_via_file`** (object): Sensitive vars passed via temp file
    - **`host_prefixes`** (array): Host environment variable prefixes to pass through (can use `"*"` to pass everything from host)

#### After Script Configuration

- **`after_script`** (object): Post-execution operations
  - **`copy_files_to_host`** (object): Copy files from container to host after execution (`host_path: container_path`)
  - **`extract_params_from_files`** (object): Extract parameters from container files (supports JSON, YAML, and ENV files)

## Output Parameters

- `params.execution_time`: Total execution time in seconds
- `params.return_code`: Container exit code
- `params.stdout`: Container stdout (if `save_stdout_to_params` enabled)
- `params.stderr`: Container stderr (if `save_stdout_to_params` enabled)
- `params.extracted_output.*`: Extracted parameters from files (if `extract_params_from_files` configured)

## Notes

- The command automatically handles container lifecycle including start, execution, and cleanup
- All host-paths (including mount paths) are resolved relative to context directory

## Adding podman executable in your image

To install and use `podman run` in your Dockerimage (`python:3.11-slim` was used as a base image, to run `Pipelines Declarative Executor`) inside usual CIs (GitHub/GitLab) following approaches worked:

### GitHub

1. `apt-get install podman nftables fuse-overlayfs`

2. ```bash
    RUN cat <<EOF > /etc/containers/storage.conf
    [storage]
    driver = "overlay"
    runroot = "/run/containers/storage"
    graphroot = "/var/lib/containers/storage"
    [storage.options]
    mount_program = "/usr/bin/fuse-overlayfs"
    EOF
    ```

3. In your workflow file, need to pass `--privileged` option

    ```yaml
   jobs:
      execute-pipeline:
        runs-on: ubuntu-latest
        container:
          image: ghcr.io/netcracker/qubership-pipelines-declarative-executor:dev_podman_engine
          options: --privileged
    ```

4. Need to run `PodmanRunImage` command with additional flags: `"additional_run_flags": "--cgroups=disabled"`

### GitLab

1. `apt-get install podman nftables slirp4netns fuse-overlayfs`

2. ```bash
    RUN cat <<EOF > /etc/containers/storage.conf
    [storage]
    driver = "overlay"
    runroot = "/run/containers/storage"
    graphroot = "/var/lib/containers/storage"
    [storage.options]
    mount_program = "/usr/bin/fuse-overlayfs"
    EOF
    ```

3. Need to run `PodmanRunImage` command with additional flags: `"additional_run_flags": "--cgroups=disabled --network slirp4netns"`
