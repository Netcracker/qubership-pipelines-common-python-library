# Qubership Pipelines Common Library

Open-source python library of clients used by Qubership pipelines/modules.

Library provides easy-to-use clients and wrappers for common devops services (e.g. Jenkins, GitLab Pipelines)

## Structure

Library is presented as a set of [clients](docs/Clients.md) with predefined operations


## Installation

* Add the following section to your dependencies to add Qubership library as a dependency in your project:
  ```toml
  [tool.poetry.dependencies]
  qubership-pipelines-common-library = "*"
  ```

* Or you can install it via `pip`:
  ```bash
  pip install qubership-pipelines-common-library
  ```