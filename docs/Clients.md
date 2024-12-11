# Library Clients Description

## JenkinsClient

1. Initialization and how to use:
   ```python
   JenkinsClient(host, user, password)
   ```
   Input params description:
   * **host** - url to Jenkins host environment (example https://self-hosted-jenkins.qubership.org )
   * **user** - username for Jenkins instance
   * **password** - password or token for Jenkins instance


2. Methods description:

* **run_pipeline(job_name, job_params)**

  Input params description:
  * **job_name** - Name of job which config required.
  * **job_params** - Dictionary with params for job start
  Job params example json:
  ```json
  {"PARAM1":"value1","PARAM2":"value2","PARAM3":"value3"}
  ```
  **NOTE: all parameters and values should be in double quotes**

  Output: -

* **get_pipeline_execution_status(build_id, job_name)**

  Input params description:
  * **build_id** - Build id which need to get
  * **job_name** - Name of job which config required.

  Output: Execution result status

* **wait_pipeline_execution(build_id, job_name, timeout_seconds, break_status_list)**

  Input params description:
  * **build_id** - Build id which need to get
  * **job_name** - Name of job which config required.
  * **timeout_seconds** - delay in seconds which execution will wait
  * **break_status_list** - list of string statuses which will break execution if execution status will be in list

  Output: 
    ```json
  {"build_id":"build_id","build_result":"build result"}
  ```

* **cancel_pipeline_execution(build_id, job_name, timeout)**

  Input params description:
  * **build_id** - Build id which need to get
  * **job_name** - Name of job which config required.
  * **timeout** - optional parameter which indicates timeout delay before stop execution, 0 by default

  Output: -


## GitClient

1. Initialization and how to use:
   ```python
   GitClient(host, username, password, email)
   ```
   Input params description:
   * **host** - url to Git host  (example https://git.qubership.org)
   * **user** - username for Git
   * **password** - password or token for Git
   * **email** - user mail


2. Methods description:
   
* **clone(repo_path, branch, temp_path)**

  Input params description:
  * **repo_path** - Path to repo which should be cloned.
  * **branch** - branch name which need to be cloned
  * **temp_path** - Path to temp folder

  Output: -

* **commit_and_push(commit_message)**

  Input params description:
  * **commit_message** - Message for commit to active repo branch.
 
  Output: -

* **get_file_content_utf8(relative_path)**

  Input params description:
  * **relative_path** - Path to file which need to get.
 
  Output:
  File content for input file path.

* **set_file_content_utf8(relative_path, content)**

  Input params description:
  * **relative_path** - Path to file which need to get.
  * **content** - file content which need to be set.
 
  Output: -

* **delete_by_path(relative_path)**

  Input params description:
  * **relative_path** - Path to file or directory which need to remove.
 
  Output: - 

* **trigger_pipeline(project_id, pipeline_params)**

  Input params description:
  * **project_id** - Git project ID or path to project.
  * **pipeline_params** - params for start pipelines
  Pipeline params example json:
  ```json
  {"ref":"master","variables":[{"key": "param_name1", "value":  "param_value1"}, {"key": "param_name2", "value":  "param_value2"}]}
  ```
  
* **cancel_pipeline_execution(project_id, pipeline_id, timeout)**

  Input params description:
  * **project_id** - Git project ID or path to project.
  * **pipeline_id** - Pipeline ID which need to cancel.
  * **timeout** - optional parameter which indicates timeout delay before stop execution, 0 by default

  Output: pipeline execution info

* **wait_pipeline_execution(project_id, pipeline_id, timeout_seconds, break_status_list)**

  Input params description:
  * **project_id** - Git project ID or path to project.
  * **pipeline_id** - Pipeline ID which need to wait.
  * **timeout_seconds** - delay in seconds which execution will wait
  * **break_status_list** - list of string statuses which will break execution if execution status will be in list

  Output: pipeline execution info

* **get_pipeline_status(project_id, pipeline_id)**

  Input params description:
  * **project_id** - Git project ID or path to project.
  * **pipeline_id** - Pipeline ID which need to get.

  Output: pipeline execution status
