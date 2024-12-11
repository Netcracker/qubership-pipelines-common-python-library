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

import logging, os, re, shutil, json, gitlab
from pathlib import Path
from time import sleep
from git import Repo

from v1.utils.utils_file import UtilsFile
from v1.execution.exec_info import ExecutionInfo

class GitClient:
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

    BREAK_STATUS_LIST = [STATUS_FAILED, STATUS_CANCELLED, STATUS_SKIPPED]

    def __init__(self, host: str, username: str, password: str, email: str = None):
        self.host = host.rstrip("/")
        self.username = username
        self.email = email
        self.password = password
        self.temp_path = None  # path to temporary folder to process files
        self.repo = None  # git repository object
        self.repo_path = None  # path to repository in GIT
        self.branch = None  # last processed branch
        self.gl = gitlab.Gitlab(url=self.host, private_token=self.password)
        logging.info("Git Client configured for %s", self.host)

    def clone(self, repo_path: str, branch: str, temp_path: str):
        repo_path = repo_path.lstrip("/").rstrip("/")
        if not repo_path:
            raise Exception("Repository path should be defined")
        if not branch:
            raise Exception("Branch should be defined")
        if not temp_path:
            raise Exception("Temporary path should be defined")
        self._cleanup_resources()
        self.repo_path = repo_path
        self.branch = branch
        self.temp_path = temp_path
        self.repo = Repo.clone_from(
            self._gen_repo_auth_url(self.host, self.username, self.password, self.repo_path),
            temp_path,
            branch=branch,
        )

    def commit_and_push(self, commit_message: str):
        if not self._is_cloned():
            raise Exception("Cannot commit without preliminary cloning")
        if not self.email:
            raise Exception("Email should be defined to commit changed")
        self.repo.git.add(all=True)
        staged_files = self.repo.index.diff('HEAD')
        if not staged_files:
            logging.info("Nothing to commit")
        else:
            self.repo.config_writer().set_value("user", "name", self.username).release()
            self.repo.config_writer().set_value("user", "email", self.email).release()
            self.repo.git.commit('-a', '-m', commit_message)
            self.repo.git.push(self.repo.remote().name, self.repo.active_branch.name)

    def get_file_content_utf8(self, relative_path: str):
        if not self._is_cloned():
            raise Exception("Cannot get file content without preliminary cloning")
        filepath = os.path.join(self.temp_path, relative_path)
        return UtilsFile.read_text_utf8(filepath)

    def set_file_content_utf8(self, relative_path: str, content: str):
        if not self._is_cloned():
            raise Exception("Cannot set file content without preliminary cloning")
        filepath = os.path.join(self.temp_path, relative_path)
        UtilsFile.write_text_utf8(filepath, content)

    def delete_by_path(self, relative_path: str):
        if not self._is_cloned():
            raise Exception("Cannot delete file without preliminary cloning")
        filepath = os.path.join(self.temp_path, relative_path)
        if Path(filepath).is_file():
            Path(filepath).unlink()
        elif Path(filepath).is_dir():
            shutil.rmtree(filepath)

    def trigger_pipeline(self, project_id: str, pipeline_params: dict):
        execution = ExecutionInfo().with_name(project_id).with_params(pipeline_params).with_status(ExecutionInfo.STATUS_UNKNOWN)
        project = self.gl.projects.get(project_id)
        pipeline = project.pipelines.create(pipeline_params)
        return execution.with_id(pipeline.get_id()).start()

    def cancel_pipeline_execution(self, execution: ExecutionInfo, timeout: float = 1.0):
        project = self.gl.projects.get(execution.get_name())
        pipeline = project.pipelines.get(execution.get_id())
        counter = 0
        while counter < timeout:
            counter += 1
            logging.info("Waiting pipeline execution timeout 1 second")
            sleep(1)
            continue
        pipeline.cancel()
        return execution.stop(ExecutionInfo.STATUS_ABORTED)

    def get_pipeline_status(self, execution: ExecutionInfo):
        project = self.gl.projects.get(execution.get_name())
        pipeline = project.pipelines.get(execution.get_id())
        if pipeline:
            json_pipeline = json.loads(pipeline.to_json())
            pipeline_url = json_pipeline["web_url"]
            pipeline_status = self._map_status(json_pipeline["status"], ExecutionInfo.STATUS_UNKNOWN)
            execution.with_url(pipeline_url)
            execution.with_status(pipeline_status)
        else:
            execution.with_url(None)
            execution.with_status(ExecutionInfo.STATUS_UNKNOWN)
            logging.error("Can't get pipeline status")
        return execution

    def wait_pipeline_execution(self, execution: ExecutionInfo, timeout_seconds: float = 10.0, break_status_list: list = None):
        if break_status_list is None:
            break_status_list = self.BREAK_STATUS_LIST
        timeout = 0
        execution.with_status(execution.get_status())
        while timeout < timeout_seconds:
            try:
                project = self.gl.projects.get(execution.get_name())
                pipeline = project.pipelines.get(execution.get_id())
                pipeline_status = json.loads(pipeline.to_json())["status"]
                execution.with_status(self._map_status(pipeline_status, ExecutionInfo.STATUS_UNKNOWN))
                if pipeline_status in break_status_list:
                    logging.info("Pipeline status: %s contains in input break status list. Stop waiting.", pipeline_status)
                    break
                else:
                    timeout += 1
                    logging.info("Waiting pipeline execution timeout 1 second")
                    sleep(1)
                    continue
            except Exception:
                timeout += 1
                logging.info("Waiting pipeline execution timeout 1 second")
                sleep(1)
                continue
        return execution

    def _gen_repo_auth_url(self, host: str, username: str, password: str, repo_path: str) -> str:
        tmp = re.split("(://)", host)
        repo_auth_url = f"{tmp[0]}{tmp[1]}{username}:{password}@{tmp[2]}/{repo_path}"
        return repo_auth_url

    def _is_cloned(self):
        return self.temp_path and self.repo

    def _cleanup_resources(self):
        if self.temp_path and Path(self.temp_path).exists():
            shutil.rmtree(self.temp_path)
        self.temp_path = None
        self.repo = None
        self.repo_path = None
        self.branch = None

    def _map_status(self, git_status: str, default_status: str):
        result = default_status
        if git_status in (GitClient.STATUS_CREATED, GitClient.STATUS_WAITING,
                          GitClient.STATUS_PREPARING, GitClient.STATUS_PENDING, GitClient.STATUS_SCHEDULED):
            result = ExecutionInfo.STATUS_NOT_STARTED
        elif git_status == GitClient.STATUS_RUNNING:
            result = ExecutionInfo.STATUS_IN_PROGRESS
        elif git_status == GitClient.STATUS_SUCCESS:
            result = ExecutionInfo.STATUS_SUCCESS
        elif git_status == GitClient.STATUS_FAILED:
            result = ExecutionInfo.STATUS_FAILED
        elif git_status in (GitClient.STATUS_CANCELLED, GitClient.STATUS_SKIPPED):
            result = ExecutionInfo.STATUS_ABORTED
        elif git_status == GitClient.STATUS_MANUAL:
            result = ExecutionInfo.STATUS_MANUAL
        return result

    def get_file_content(self, project_id: str, ref: str, file_path: str):
        project = self.gl.projects.get(project_id)
        return project.files.get(file_path=file_path, ref=ref).decode().decode("utf-8")
