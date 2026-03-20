[![PyPI](https://img.shields.io/pypi/v/qubership-pipelines-common-library)](https://pypi.org/project/qubership-pipelines-common-library/)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/qubership-pipelines-common-library)
![Build](https://github.com/Netcracker/qubership-pipelines-common-python-library/actions/workflows/python-publish.yml/badge.svg)
![Repo Size](https://img.shields.io/github/repo-size/Netcracker/qubership-pipelines-common-python-library)

# Qubership Pipelines Common Library

Open-source python library of clients used by Qubership pipelines/modules.

Library provides easy-to-use clients and wrappers for common DevOps services (e.g. Jenkins, MiniO, GitLab Pipelines)

## Using Execution Commands

Sample implementation of CLI commands using this library is available at [qubership-pipelines-cli-command-samples](https://github.com/Netcracker/qubership-pipelines-cli-command-samples)

Library itself also provides commands since `v2.0.0`, and there's [a separate documentation](./docs/using_commands.md) on recommended ways to integrate and use them in your applications.

It includes reference python implementation along with the [Development Guide](https://github.com/Netcracker/qubership-pipelines-cli-command-samples/blob/main/docs/development.md)

## Structure

Library is presented as a set of clients with predefined operations

Auto-generated reference (via mkdocs) is available on [this repo's GitHub Pages](https://netcracker.github.io/qubership-pipelines-common-python-library/mkdocs)

## Installation

- Add the following section to your dependencies to add Qubership library as a dependency in your project:

  ```toml
  [tool.poetry.dependencies]
  qubership-pipelines-common-library = "*"
  ```

- Or you can install it via `pip`:

  ```bash
  pip install qubership-pipelines-common-library
  ```
