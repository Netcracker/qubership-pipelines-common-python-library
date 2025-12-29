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

import logging, jenkins, time

from pathlib import Path
from qubership_pipelines_common_library.v1.execution.exec_info import ExecutionInfo
from qubership_pipelines_common_library.v1.utils.utils_file import UtilsFile


class JenkinsClient:

    # statuses taken from https://github.com/jenkinsci/jenkins/blob/master/core/src/main/java/hudson/model/Result.java
    STATUS_SUCCESS = "SUCCESS"
    STATUS_UNSTABLE = "UNSTABLE"
    STATUS_FAILURE = "FAILURE"
    STATUS_ABORTED = "ABORTED"
    STATUS_NOT_BUILT = "NOT_BUILT"

    BUILD_ARTIFACTS_ZIP_PATH = "*zip*/archive.zip"

    def __init__(self, host: str, user: str, password: str):
        """
        This class is deprecated and will be removed in v3.0.0. Use class from v2 module instead.
        Arguments:
            host (str): Jenkins host URL
            user (str): User used in auth request
            password (str): Token used in auth request
        """
        if self.__class__ == JenkinsClient:
            import warnings
            warnings.warn(
                "v1.jenkins_client.JenkinsClient is deprecated since v2.0.0 and will be removed in v3.0.0. "
                "Use v2.jenkins.jenkins_client.JenkinsClient instead.",
                DeprecationWarning,
                stacklevel=2
            )
        self.url = host
        self.user = user
        self.token = password
        self.server = jenkins.Jenkins(self.url, username=self.user, password=self.token)
        who_am_i = self.server.get_whoami()
        jenkins_version = self.server.get_version()
        logging.debug("JenkinsClient initialized for user '%s' and Jenkins version is '%s'",
                      who_am_i, jenkins_version)

    def run_pipeline(self, job_name: str, job_params: dict, timeout_seconds: float = 180.0, wait_seconds: float = 1.0):
        """"""
        logging.debug("Run job with name '%s', params '%s' and timeout '%s' seconds", job_name, job_params, timeout_seconds)
        execution = ExecutionInfo().with_name(job_name).with_params(job_params).with_status(ExecutionInfo.STATUS_UNKNOWN)
        if not self.server.job_exists(job_name):
            logging.error("Job '%s' is not found! Please verify job name", job_name)
            return execution
        execution.with_status(ExecutionInfo.STATUS_NOT_STARTED)
        count = 0
        queue_id = 0
        while queue_id == 0:
            try:
                queue_id = self.server.build_job(job_name, job_params)
                logging.info("Job was successfully added to the queue with id '%s'", queue_id)
            except Exception:
                if count < timeout_seconds:
                    logging.info("Job is not queued yet, waiting %s of %s", count, timeout_seconds)
                    count += wait_seconds
                    time.sleep(wait_seconds)
                    continue
                else:
                    logging.error("Wasn't able to queue the job within %s seconds", timeout_seconds)
                    return execution
        count = 0
        build_id = 0
        if timeout_seconds < 1:
            logging.debug("Job put to queue, not fetching job id in async mode...")
            return execution.start()
        while build_id == 0:
            try:
                queue_info = self.server.get_queue_item(queue_id)
                logging.debug("Queue info for the job: %s", queue_info)
                build_id = int(queue_info["executable"]["number"])
            except Exception:
                if count < timeout_seconds:
                    logging.info("Job is not started yet, waiting %s of %s", count, timeout_seconds)
                    count += 5
                    time.sleep(5)
                    continue
                else:
                    logging.error("Wasn't able to start job within %s seconds", timeout_seconds)
                    return execution
        logging.info("Job '%s' started with id '%s'", job_name, build_id)
        return execution.with_id(build_id).start()

    def get_pipeline_execution_status(self, execution: ExecutionInfo, timeout_seconds: float = 30.0, wait_seconds: float = 1.0):
        """"""
        build_info = self._get_build_info(execution, timeout_seconds, wait_seconds)
        logging.debug("Job info: %s", build_info)
        if build_info:
            execution.with_url(build_info["url"])
            execution.with_status(self._map_status(build_info["result"], ExecutionInfo.STATUS_UNKNOWN))
        else:
            execution.with_url(None)
            execution.with_status(ExecutionInfo.STATUS_UNKNOWN)
            logging.error("Can't get job result within %s seconds", timeout_seconds)
        return execution

    def wait_pipeline_execution(self, execution: ExecutionInfo, timeout_seconds: float = 180.0, wait_seconds: float = 1.0):
        """"""
        count_seconds = 0
        last_log_time = time.perf_counter()
        estimated_max_attempts = timeout_seconds // wait_seconds
        retries = 0
        while count_seconds < timeout_seconds:
            try:
                build_info = self.server.get_build_info(execution.get_name(), execution.get_id(), depth=0)
                logging.debug("Job info: %s", build_info)
                build_result = build_info["result"]

                if "inProgress" in build_info: # Jenkins version >= 2.375. Use 'inProgress' property
                    is_job_stopped = build_info["inProgress"] is False and build_result
                else:                          # Jenkins version <= 2.369. Use 'building' property
                    is_job_stopped = build_info["building"] is False and build_result

                if is_job_stopped:
                    logging.info("Job is stopped with result '%s'", build_result)
                    build_url = build_info["url"]
                    build_status = self._map_status(build_result, ExecutionInfo.STATUS_UNKNOWN)
                    execution.with_url(build_url).stop(build_status)
                    break
            except Exception:
                execution.with_status(ExecutionInfo.STATUS_UNKNOWN)
                logging.error("Failed to get information about job with name '%s' and id '%s'", execution.get_name(), execution.get_id())
            now = time.perf_counter()
            retries += 1
            if now - last_log_time >= 10.0:
                logging.info(f"Made [{retries} of {estimated_max_attempts}] retries. Waiting pipeline execution {count_seconds} of {timeout_seconds}")
                last_log_time = now
            count_seconds += wait_seconds
            time.sleep(wait_seconds)
        if count_seconds >= timeout_seconds:
            execution.with_status(ExecutionInfo.STATUS_TIMEOUT)
        return execution

    def cancel_pipeline_execution(self, execution: ExecutionInfo, timeout_seconds: float = 30.0, wait_seconds: float = 1.0):
        """"""
        self.server.stop_build(execution.get_name(), execution.get_id())
        count = 0
        while count < timeout_seconds:
            logging.info("Waiting while job stop %s of %s", count, timeout_seconds)
            count += wait_seconds
            time.sleep(wait_seconds)
        return execution.stop(ExecutionInfo.STATUS_ABORTED)

    def get_pipeline_execution_artifacts(self, execution: ExecutionInfo, timeout_seconds: float = 30.0, wait_seconds: float = 1.0):
        """Returns list of artifact relative paths"""
        build_info = self._get_build_info(execution, timeout_seconds, wait_seconds)
        logging.debug("Job info: %s", build_info)
        if build_info:
            artifacts = build_info["artifacts"]
            return [artifact["relativePath"] for artifact in artifacts]
        else:
            logging.error("Can't get job artifacts within %s seconds", timeout_seconds)
            return []

    def save_pipeline_execution_artifact_to_file(self, execution: ExecutionInfo, artifact_path: str, file_path: str):
        """"""
        artifact_bytes = self.server.get_build_artifact_as_bytes(execution.get_name(), execution.get_id(), artifact_path)
        UtilsFile.create_parent_dirs(file_path)
        # Jenkins might return gzipped artifacts:
        if len(artifact_bytes) >= 2 and artifact_bytes[0] == 0x1f and artifact_bytes[1] == 0x8b:
            try:
                import io, gzip
                with gzip.GzipFile(fileobj=io.BytesIO(artifact_bytes)) as f:
                    decompressed_bytes = f.read()
                Path(file_path).write_bytes(decompressed_bytes)
            except Exception as e:
                logging.warning(f"Failed to decompress gzip, writing raw: {e}")
                Path(file_path).write_bytes(artifact_bytes)
        else:
            Path(file_path).write_bytes(artifact_bytes)

    def _get_build_info(self, execution: ExecutionInfo, timeout_seconds: float = 30.0, wait_seconds: float = 1.0):
        count = 0
        while count < timeout_seconds:
            try:
                build_info = self.server.get_build_info(execution.get_name(), execution.get_id(), depth=0)
                return build_info
            except Exception:
                logging.info("Can't get job result, waiting %s of %s", count, timeout_seconds)
                count = count + wait_seconds
                time.sleep(wait_seconds)
                continue
        return None

    def _map_status(self, jenkins_status: str, def_status: str):
        if jenkins_status == JenkinsClient.STATUS_SUCCESS:
            return ExecutionInfo.STATUS_SUCCESS
        if jenkins_status == JenkinsClient.STATUS_UNSTABLE:
            return ExecutionInfo.STATUS_UNSTABLE
        if jenkins_status == JenkinsClient.STATUS_FAILURE:
            return ExecutionInfo.STATUS_FAILED
        if jenkins_status == JenkinsClient.STATUS_ABORTED:
            return ExecutionInfo.STATUS_ABORTED
        if jenkins_status == JenkinsClient.STATUS_NOT_BUILT:
            return ExecutionInfo.STATUS_NOT_STARTED
        return def_status
