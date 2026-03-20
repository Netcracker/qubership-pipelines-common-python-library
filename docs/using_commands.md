# Using Commands

While you can integrate provided commands directly into your code,
original intended way to use them was building `click` CLI applications,
where each individual `click.command` corresponds to one `ExecutionCommand`.

This library provides `@utils_cli` decorator that facilitates this scenario.

## Wrapping Execution Commands with `click` decorator

In your `__main__.py` file with `@click.group` declared, you can add different Execution Commands (sample application that uses commands is [qubership-pipelines-cli-command-samples](https://github.com/Netcracker/qubership-pipelines-cli-command-samples)).

Local import of commands is recommended for big applications containing lots of commands to significantly improve load times (applicable when using commands with heavy dependencies)

```python
@cli.command("github-run-pipeline")
@utils_cli
def __github_run_pipeline(**kwargs):
    from qubership_pipelines_common_library.v2.github.github_run_pipeline_command import GithubRunPipeline
    command = GithubRunPipeline(**kwargs)
    command.run()
```

## @utils_cli decorator

This decorator aggregates and provides generic `click` configuration options:

* `--log-level` - allows to specify log level for console output and `execution.log` in commands directory. `full.log` will always contain `DEBUG` level logs. Supported values: `DEBUG`, `INFO` (default one), `WARNING`, `ERROR`, `CRITICAL`
* `--context_path` - specify path to `context.yaml` file (also defaults to `context.yaml` in current directory) if working with one (also used by Pipelines Declarative Executor)
* `--input_params` or `-p` - allows to pass insecure params explicitly, without generating context-structure and passing context-file (will generate context-structure implicitly in a temp folder). Use via `--input_params=params.test_param=test_value` or `-p params.test_param=test_value`
* `--input_params_secure` or `-s` - allows to pass secure params explicitly, same logic applies as with insecure params, but secure params are masked when logged.
* `--cli-output-mode` - allows to change output mode of CLI to make it output only resulting params dictionary in different formats, instead of default logging (can be used for integrating with other CLI applications). Supports different modes: `OFF` (default one), `INSECURE_PARAMS`, `SECURE_PARAMS`, `MERGED_PARAMS` (merges both insecure and secure params, with secure values taking precedence)
* `--cli-output-format` - allows to change output format, when using one of `cli-output-modes`. Supported formats: `YAML` (default one), `JSON`, `PRETTY_JSON`

## Invoking resulting CLI

1. Calling commands with existing prepared context:

    ```bash
    python YOUR_CLI_APP github-run-pipeline --context-path=./data/context.yaml
    ```

2. Creating context implicitly by passing input params:

    ```bash
    python YOUR_CLI_APP github-run-pipeline -p params.pipeline_repo_name=qubership-test-pipelines -p params.pipeline_workflow_file_name=test.yaml -s systems.url=https://github.com
    ```

3. Calling commands with output mode and default format:

    ```bash
    python YOUR_CLI_APP your-command-name --context-path=./data/context.yaml --cli-output-mode=INSECURE_PARAMS
    ```

    Returns following STDOUT:

    ```yaml
    kind: AtlasModuleParamsInsecure
    apiVersion: v1
    params:
      some_insecure_param_0: zeppelin_meadow_echo
      some_insecure_param_1: cinnamon_yogurt_violin
    files: {}
    systems: {}
    ```

4. Calling commands with output mode and specific format:

    ```bash
    python YOUR_CLI_APP your-command-name --context-path=./data/context.yaml --cli-output-mode=INSECURE_PARAMS --cli-output-format=PRETTY_JSON
    ```

    Returns following STDOUT:

    ```json
    {
      "kind": "AtlasModuleParamsInsecure",
      "apiVersion": "v1",
      "params": {
        "some_insecure_param_0": "zeppelin_meadow_echo",
        "some_insecure_param_1": "cinnamon_yogurt_violin"
      },
      "files": {},
      "systems": {}
    }
    ```
