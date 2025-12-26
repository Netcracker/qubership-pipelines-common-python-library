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

import logging, gitlab, time
from pathlib import Path

from gitlab import GitlabGetError
from qubership_pipelines_common_library.v1.execution.exec_info import ExecutionInfo


class GitlabClient:
    # statuses taken from https://docs.gitlab.com/ee/api/pipelines.html
    STATUS_CREATED = "created"
    STATUS_WAITING = "waiting_for_resource"
    STATUS_PREPARING = "preparing"
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "canceled"
    STATUS_SKIPPED = "skipped"
    STATUS_MANUAL = "manual"
    STATUS_SCHEDULED = "scheduled"

    BREAK_STATUS_LIST = [STATUS_SUCCESS, STATUS_FAILED, STATUS_CANCELLED, STATUS_SKIPPED]

    def __init__(self, host: str, username: str, password: str, email: str = None, **kwargs):
        """
        This class is deprecated and will be removed in v3.0.0. Use class from v2 module instead.
        Arguments:
            host (str): Gitlab instance URL
            username (str): User used in auth request, might be empty string if no auth is required
            password (str): Token used in auth request
            email (str): Email used when committing changes using API
            **kwargs (Any): will be passed into Gitlab API constructor
        """
        if self.__class__ == GitlabClient:
            import warnings
            warnings.warn(
                "v1.gitlab_client.GitlabClient is deprecated since v2.0.0 and will be removed in v3.0.0. "
                "Use v2.gitlab.gitlab_client.GitlabClient instead.",
                DeprecationWarning,
                stacklevel=2
            )
        self.host = host.rstrip("/")
        self.username = username
        self.email = email
        self.password = password
        self.gl = gitlab.Gitlab(url=self.host, private_token=self.password, **kwargs)
        logging.info("Gitlab Client configured for %s", self.host)

    def get_file_content(self, project_id: str, ref: str, file_path: str):
        """"""
        return self.gl.projects.get(project_id, lazy=True).files \
            .get(file_path=file_path, ref=ref).decode().decode("utf-8")

    def create_file(self, project_id: str, file_path: str, content: str, ref: str, commit_message: str):
        """"""
        logging.debug(f"Creating file {file_path} on branch {ref}...")
        self.gl.projects.get(project_id, lazy=True).files.create(
            {'file_path': file_path,
             'branch': ref,
             'content': content,
             'author_email': self.email,
             'commit_message': commit_message
             }
        )

    def update_file(self, project_id: str, file_path: str, content: str, ref: str,
                    commit_message: str, create_if_not_exists: bool = False):
        """"""
        try:
            logging.debug(f"Updating file {file_path} on branch {ref}...")
            file = self.gl.projects.get(project_id, lazy=True).files.get(file_path=file_path, ref=ref)
            file.content = content
            file.save(branch=ref, commit_message=commit_message, author_email=self.email)
        except GitlabGetError as e:
            if e.response_code == 404 and create_if_not_exists:
                self.create_file(project_id=project_id, file_path=file_path, content=content, ref=ref,
                                 commit_message=commit_message)
            else:
                raise

    def delete_file(self, project_id: str, file_path: str, ref: str, commit_message: str):
        """"""
        logging.debug(f"Deleting file {file_path} on branch {ref}...")
        self.gl.projects.get(project_id, lazy=True).files \
            .get(file_path=file_path, ref=ref).delete(branch=ref, commit_message=commit_message)

    def get_latest_commit_id(self, project_id: str, ref: str):
        """"""
        project = self.gl.projects.get(project_id, lazy=True)
        latest_commit = project.commits.list(ref_name=ref, per_page=1, get_all=False)[0]
        return latest_commit.id

    def get_file_commit_info(self, project_id: str, ref: str, file_path: str):
        """Returns dict with 'commit_id' and 'last_commit_id' from Gitlab API"""
        project = self.gl.projects.get(project_id, lazy=True)
        file = project.files.get(file_path=file_path, ref=ref)
        return {
            "commit_id": file.commit_id,
            "last_commit_id": file.last_commit_id,
        }

    def trigger_pipeline(self, project_id: str, pipeline_params: dict):
        """"""
        project = self.gl.projects.get(project_id, lazy=True)
        pipeline = project.pipelines.create(pipeline_params)
        logging.info(f"Pipeline successfully started at {pipeline.web_url}")
        return ExecutionInfo().with_name(project_id).with_id(pipeline.get_id()) \
            .with_url(pipeline.web_url).with_params(pipeline_params) \
            .start()

    def cancel_pipeline_execution(self, execution: ExecutionInfo, timeout: float = 1.0):
        """"""
        project = self.gl.projects.get(execution.get_name(), lazy=True)
        pipeline = project.pipelines.get(execution.get_id())
        counter = 0
        while counter < timeout:
            counter += 1
            logging.info("Waiting pipeline execution timeout 1 second")
            time.sleep(1)
            continue
        pipeline.cancel()
        return execution.stop(ExecutionInfo.STATUS_ABORTED)

    def get_pipeline_status(self, execution: ExecutionInfo):
        """"""
        project = self.gl.projects.get(execution.get_name(), lazy=True)
        pipeline = project.pipelines.get(execution.get_id())
        if pipeline:
            execution.with_status(self._map_status(pipeline.status, ExecutionInfo.STATUS_UNKNOWN))
        else:
            execution.with_status(ExecutionInfo.STATUS_UNKNOWN)
            logging.error("Can't get pipeline status")
        return execution

    def wait_pipeline_execution(self, execution: ExecutionInfo, timeout_seconds: float = 180.0,
                                break_status_list: list = None, wait_seconds: float = 1.0):
        """"""
        if break_status_list is None:
            break_status_list = self.BREAK_STATUS_LIST
        count_seconds = 0
        last_log_time = time.perf_counter()
        estimated_max_attempts = timeout_seconds // wait_seconds
        retries = 0
        execution.with_status(execution.get_status())
        while count_seconds < timeout_seconds:
            try:
                project = self.gl.projects.get(execution.get_name(), lazy=True)
                pipeline = project.pipelines.get(execution.get_id())
                execution.with_status(self._map_status(pipeline.status, ExecutionInfo.STATUS_UNKNOWN))
                if pipeline.status in break_status_list:
                    logging.info(f"Pipeline status: '{pipeline.status}' contains in input break status list. Stop waiting.")
                    execution.stop()
                    break
            except Exception:
                pass
            now = time.perf_counter()
            retries += 1
            if now - last_log_time >= 10.0:
                logging.info(f"Made [{retries} of {estimated_max_attempts}] retries. Waiting pipeline execution {count_seconds} of {timeout_seconds}")
                last_log_time = now
            count_seconds += wait_seconds
            time.sleep(wait_seconds)
        return execution

    @staticmethod
    def get_repo_branch_path(url: str, branch: str = "main"):
        """Extracts 'repo', 'branch' and 'path' parts from possible Gitlab URLs. Needs to know branch beforehand"""
        for part in ["/-/raw/", "/-/blob/", "/-/tree/"]:
            pos1 = url.find(part)
            pos2 = url.find("/", pos1 + len(part) + len(branch))
            if pos1 > 0 and pos2 > 0:
                return {"repo": url[:pos1], "branch": url[pos1 + len(part):pos2], "path": url[pos2 + 1:]}
        return None

    def get_default_branch(self, project_id: str) -> str:
        return self.gl.projects.get(project_id).default_branch

    def get_latest_pipeline_id(self, project_id: str, ref: str) -> int | str:
        project = self.gl.projects.get(project_id, lazy=True)
        return project.pipelines.latest(ref=ref).get_id()

    def get_latest_job(self, project_id: str, pipeline_id: str):
        project = self.gl.projects.get(project_id, lazy=True)
        pipeline = project.pipelines.get(pipeline_id, lazy=True)

        jobs = pipeline.jobs.list(get_all=True)
        logging.debug(f"All jobs from the pipeline: {jobs}")

        # get jobs from downstream pipelines
        bridges = pipeline.bridges.list(get_all=True)
        logging.debug(f"Bridges: {bridges}")
        for bridge in bridges:
            downstream_pipeline_data = bridge.downstream_pipeline
            downstream_project = self.gl.projects.get(downstream_pipeline_data.get('project_id'), lazy=True)
            logging.debug(f"Getting jobs from a downstream pipeline: {downstream_pipeline_data.get('id')}...")
            downstream_pipeline = downstream_project.pipelines.get(downstream_pipeline_data.get('id'))
            jobs.extend(downstream_pipeline.jobs.list(get_all=True))

        # get jobs from child pipelines
        child_pipelines = project.pipelines.list(ref=f"downstream/{pipeline_id}", source="pipeline", all=True)
        logging.debug(f"Child pipelines: {child_pipelines}")
        for child_pipeline in child_pipelines:
            logging.debug(f"Getting jobs from a child pipeline: {child_pipeline.id}...")
            child_jobs = child_pipeline.jobs.list(get_all=True)
            jobs.extend(child_jobs)

        logging.debug(f"All jobs (+ jobs from downstream pipelines): {jobs}")
        jobs = [j for j in jobs if j.started_at]
        jobs = sorted(jobs, key=lambda j: j.started_at, reverse=True)
        return jobs[0] if jobs else None

    def download_job_artifacts(self, project_id, job_id, local_dir):
        project = self.gl.projects.get(project_id, lazy=True)
        job = project.jobs.get(job_id, lazy=True)
        local_file = Path(local_dir, f"{job_id}.zip")
        with local_file.open('wb') as f:
            try:
                job.artifacts(streamed=True, action=f.write)
            except gitlab.GitlabGetError as e:
                if e.response_code == 404:
                    logging.warning(f"No artifacts for job {job_id}")
                    return None
                else:
                    raise
        logging.info(f"Artifacts downloaded to {local_file}")
        return local_file

    @staticmethod
    def _cast_to_string(value) -> str:
        if isinstance(value, str):
            return value
        if value is None:
            return ''
        if isinstance(value, bool):
            return 'true' if value else 'false'
        return str(value)

    def _map_status(self, git_status: str, default_status: str):
        result = default_status
        if git_status in (GitlabClient.STATUS_CREATED, GitlabClient.STATUS_WAITING,
                          GitlabClient.STATUS_PREPARING, GitlabClient.STATUS_PENDING, GitlabClient.STATUS_SCHEDULED):
            result = ExecutionInfo.STATUS_NOT_STARTED
        elif git_status == GitlabClient.STATUS_RUNNING:
            result = ExecutionInfo.STATUS_IN_PROGRESS
        elif git_status == GitlabClient.STATUS_SUCCESS:
            result = ExecutionInfo.STATUS_SUCCESS
        elif git_status == GitlabClient.STATUS_FAILED:
            result = ExecutionInfo.STATUS_FAILED
        elif git_status in (GitlabClient.STATUS_CANCELLED, GitlabClient.STATUS_SKIPPED):
            result = ExecutionInfo.STATUS_ABORTED
        elif git_status == GitlabClient.STATUS_MANUAL:
            result = ExecutionInfo.STATUS_MANUAL
        return result

    # Related static methods, with direct REST access
    @staticmethod
    def is_gitlab_project_exist(gitlab_url, gitlab_project, gitlab_token):
        """"""
        import requests
        headers = {"PRIVATE-TOKEN": gitlab_token}
        request = f"{gitlab_url}/api/v4/projects/{requests.utils.quote(gitlab_project, safe='')}"
        logging.debug(f"Sending '{request}' request...")
        response = requests.get(request, headers=headers)
        if response.status_code == 200:
            return True
        else:
            logging.error(f"Error {response.status_code}: {response.text}")
        return False

    @staticmethod
    def search_group_id(gitlab_url, gitlab_project, gitlab_token):
        """"""
        import requests
        headers = {"PRIVATE-TOKEN": gitlab_token}
        request = f"{gitlab_url}/api/v4/groups?search={gitlab_project}"
        logging.debug(f"Sending '{request}' request...")
        response = requests.get(request, headers=headers)
        if response.status_code == 200:
            groups = response.json()
            for group in groups:
                if group.get("full_path") == gitlab_project:
                    return group["id"]
        else:
            logging.error(f"Error {response.status_code}: {response.text}")

    @staticmethod
    def create_internal_gitlab_project(gitlab_url, gitlab_token, group_id, repo_name, repo_branch, visibility="internal"):
        """"""
        import requests
        headers = {"PRIVATE-TOKEN": gitlab_token, "Content-Type": "application/json"}
        data = {
            "name": repo_name,
            "namespace_id": group_id,
            "visibility": visibility,
            "default_branch": repo_branch
        }
        request = f"{gitlab_url}/api/v4/projects"
        logging.debug(f"Sending '{request}' request...")
        response = requests.post(request, headers=headers, json=data)
        if response.status_code == 201:
            response_json = response.json()
            logging.info(f"Gitlab project was created. Url: '{response_json['web_url']}'")
            GitlabClient.make_first_commit_to_gitlab_project(
                gitlab_url=gitlab_url,
                gitlab_token=gitlab_token,
                project_id=response_json['id'],
                repo_branch=repo_branch
            )
        else:
            logging.error(f"Error {response.status_code}: {response.text}")

    @staticmethod
    def make_first_commit_to_gitlab_project(gitlab_url, gitlab_token, project_id, repo_branch):
        """"""
        import requests
        logging.debug("Making first commit...")
        headers = {"PRIVATE-TOKEN": gitlab_token, "Content-Type": "application/json"}
        commit_payload = {
            "branch": repo_branch,
            "commit_message": "Initial commit",
            "actions": [
                {
                    "action": "create",
                    "file_path": "README.md",
                    "content": "# This is an automatically created project"
                }
            ]
        }

        response = requests.post(
            f"{gitlab_url}/api/v4/projects/{project_id}/repository/commits",
            headers=headers,
            json=commit_payload
        )
        if response.status_code == 201:
            logging.info("Commit successfull")
        else:
            logging.error(f"Error {response.status_code}: {response.text}")
