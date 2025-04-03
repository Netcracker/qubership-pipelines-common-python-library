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

import logging
from datetime import datetime, timezone
from github import Github, Auth
from time import sleep
from qubership_pipelines_common_library.v1.execution.exec_info import ExecutionInfo


class GithubClient:

    # statuses and conclusions:
    # from https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/about-status-checks#check-statuses-and-conclusions
    STATUS_COMPLETED = "completed"
    STATUS_FAILURE = "failure"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_PENDING = "pending"
    STATUS_QUEUED = "queued"

    CONCLUSION_SUCCESS = "success"
    CONCLUSION_FAILURE = "failure"
    CONCLUSION_CANCELLED = "cancelled"
    CONCLUSION_SKIPPED = "skipped"
    CONCLUSION_ACTION_REQUIRED = "action_required"

    BREAK_STATUS_LIST = [STATUS_COMPLETED, STATUS_FAILURE]

    def __init__(self, token: str = None, api_url: str = None, **kwargs):
        """
        Arguments:
            token (str): Token used in auth request
            api_url (str): Optional Github Enterprise API URL, leave empty if using github.com
            **kwargs (Any): will be passed into Github API constructor
        """
        self.auth = Auth.Token(token) if token else None
        if api_url:
            self.gh = Github(base_url=api_url, auth=self.auth, **kwargs)
        else:
            self.gh = Github(auth=self.auth, **kwargs)
        logging.info("Github Client configured")

    def trigger_workflow(self, owner: str, repo_name: str, workflow_file_name: str, branch: str, pipeline_params: dict,
                         timeout_seconds: float = 30.0, wait_seconds: float = 3.0):
        """ There's currently no reliable way to get ID of triggered workflow, dispatch is async and doesn't return anything
        As a workaround - we start looking for newly created runs of that workflow, filtering them as much as possible """
        workflow = self.gh.get_repo(f"{owner}/{repo_name}", lazy=True).get_workflow(workflow_file_name)
        dispatch_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        execution = ExecutionInfo()
        is_created = workflow.create_dispatch(ref=branch, inputs=pipeline_params)
        logging.info(f"Workflow Dispatch event for {workflow_file_name} is sent, workflow is created: {is_created}")
        if is_created:
            current_timeout = 0
            while current_timeout < timeout_seconds:
                runs_list = workflow.get_runs(event="workflow_dispatch", created=f">={dispatch_time}", branch=branch)
                if runs_list.totalCount > 0:
                    created_run = runs_list.get_page(0).pop()
                    logging.info(f"Pipeline successfully started at {created_run.html_url}")
                    return execution.with_name(created_run.name).with_id(created_run.id) \
                        .with_url(created_run.html_url).with_params(pipeline_params) \
                        .start()
                current_timeout += wait_seconds
                logging.info(f"Waiting for triggered workflow run to start... Timeout {wait_seconds} seconds")
                sleep(wait_seconds)
            logging.error(f"Could not find created run's ID in time ({timeout_seconds}s)")
        else:
            logging.error(f"Workflow {workflow_file_name} wasn't created")
        return execution

    def get_workflow_run_status(self, execution: ExecutionInfo):
        """"""
        repo_full_name = self._get_repo_full_name(execution)
        if not repo_full_name:
            return execution.with_status(ExecutionInfo.STATUS_UNKNOWN)
        run = self.gh.get_repo(repo_full_name).get_workflow_run(int(execution.get_id()))
        if run:
            execution.with_status(self._map_status_and_conclusion(run.status, run.conclusion, ExecutionInfo.STATUS_UNKNOWN))
        else:
            execution.with_status(ExecutionInfo.STATUS_UNKNOWN)
            logging.error("Can't get workflow run status")
        return execution

    def wait_workflow_run_execution(self, execution: ExecutionInfo, timeout_seconds: float = 60.0,
                                break_status_list: list = None, wait_seconds: float = 10.0):
        """"""
        if break_status_list is None:
            break_status_list = self.BREAK_STATUS_LIST
        repo_full_name = self._get_repo_full_name(execution)
        if not repo_full_name:
            return execution.with_status(ExecutionInfo.STATUS_UNKNOWN)
        timeout = 0
        while timeout < timeout_seconds:
            try:
                run = self.gh.get_repo(repo_full_name).get_workflow_run(int(execution.get_id()))
                execution.with_status(self._map_status_and_conclusion(run.status, run.conclusion, ExecutionInfo.STATUS_UNKNOWN))
                if run.status in break_status_list:
                    logging.info(f"Workflow Run status: '{run.status}' is present in input break statuses list. Stop waiting.")
                    execution.stop()
                    break
            except:
                pass
            timeout += wait_seconds
            logging.info(f"Waiting workflow run execution timeout {wait_seconds} seconds")
            sleep(wait_seconds)
            continue
        return execution

    def cancel_workflow_run_execution(self, execution: ExecutionInfo, timeout: float = 1.0):
        """"""
        repo_full_name = self._get_repo_full_name(execution)
        if not repo_full_name:
            return execution
        run = self.gh.get_repo(repo_full_name).get_workflow_run(int(execution.get_id()))
        counter = 0
        while counter < timeout:
            counter += 1
            logging.info("Waiting pipeline execution timeout 1 second")
            sleep(1)
        run.cancel()
        return execution.stop(ExecutionInfo.STATUS_ABORTED)

    def _map_status_and_conclusion(self, status: str, conclusion: str, default_status: str):
        logging.info(f"status: {status}, conclusion: {conclusion}")
        result = default_status
        if status in (GithubClient.STATUS_QUEUED, GithubClient.STATUS_PENDING):
            result = ExecutionInfo.STATUS_NOT_STARTED
        elif status == GithubClient.STATUS_IN_PROGRESS:
            result = ExecutionInfo.STATUS_IN_PROGRESS
        elif status == GithubClient.STATUS_FAILURE:
            result = ExecutionInfo.STATUS_FAILED
        elif status == GithubClient.STATUS_COMPLETED:
            if conclusion == GithubClient.CONCLUSION_SUCCESS:
                result = ExecutionInfo.STATUS_SUCCESS
            elif conclusion == GithubClient.CONCLUSION_FAILURE:
                result = ExecutionInfo.STATUS_FAILED
            elif conclusion in (GithubClient.CONCLUSION_CANCELLED, GithubClient.CONCLUSION_SKIPPED):
                result = ExecutionInfo.STATUS_ABORTED
            elif conclusion == GithubClient.CONCLUSION_ACTION_REQUIRED:
                result = ExecutionInfo.STATUS_MANUAL
        return result

    def _get_repo_full_name(self, execution: ExecutionInfo):
        if not execution.get_id() or not execution.get_url():
            logging.error("Can't get workflow run - empty run id or url in ExecutionInfo!")
            return None
        url_parts = execution.get_url().split("://")[1].split("/")
        return f"{url_parts[1]}/{url_parts[2]}"
