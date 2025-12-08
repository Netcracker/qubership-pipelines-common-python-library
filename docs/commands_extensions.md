# Execution Commands Extensions

Version v2.0.0 introduced extension points in `ExecutionCommand` contract, allowing you to inject custom logic before and after a command's main execution.

You can create reusable actions that automatically run at specific points in a command's lifecycle without modifying the command's core implementation.

## How It Works

When an `ExecutionCommand` runs, it follows a strict lifecycle.
If you provide `pre_execute_actions` and/or `post_execute_actions` to the command's constructor, they will be executed at their respective lifecycle stages, in the order they were provided.

```text
Command.run()
    ├── _log_input_params()
    ├── _validate()
    ├── **_pre_execute()**    ← Your extensions run here
    ├── _execute()            ← Main command logic
    ├── **_post_execute()**   ← Your extensions run here
    └── _exit()
```

## Usage sample

Sample dummy extensions for unit-testing are provided in this repository in `test_command_extensions.py`.

You can find there `OverrideParam1PreExt` pre-execute action and `OverrideResultPostExt` post-execute action (although pre- and post- actions contract is the same).

They are added to command in its constructor:

```python
cmd = SampleExtendableCommand(input_params=test_input_params,
                              pre_execute_actions=[OverrideParam1PreExt()],
                              post_execute_actions=[OverrideResultPostExt()])
```

## New parameters in `ExecutionCommand` class

| Parameter              | Type                              | Description                           | Default |
|------------------------|-----------------------------------|---------------------------------------|---------|
| `pre_execute_actions`  | `List[ExecutionCommandExtension]` | Extensions to run before `_execute()` | `None`  |
| `post_execute_actions` | `List[ExecutionCommandExtension]` | Extensions to run after `_execute()`  | `None`  |

## `ExecutionCommandExtension` Abstract Base Class

The interface all extensions must implement.

| Method                  | Returns                     | Description                                            |
|-------------------------|-----------------------------|--------------------------------------------------------|
| `with_command(command)` | `ExecutionCommandExtension` | Injects the command and its context into the extension |
| `execute()`             | `None`                      | Abstract - Contains the extension's core logic         |

## Extensions inside `_execute()`

Some commands might provide alternative extension points, e.g. - `GithubRunPipeline` and `GitlabRunPipeline` commands have extensions in form of `PipelineDataImporter` contract.

These extensions will be specific to their respective commands, and invoked according to inner business logic of them, but they still might be shared across similar commands.

In this case these extension points are described inside commands themselves.
