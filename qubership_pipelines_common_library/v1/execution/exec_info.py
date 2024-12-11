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

from datetime import datetime


class ExecutionInfo:
    STATUS_UNKNOWN = "UNKNOWN"  # pipeline status is unknown, because cannot be retrieved
    STATUS_TIMEOUT = "TIMEOUT"  # timeout is reached during pipeline awaiting
    STATUS_NOT_STARTED = "NOT STARTED"  # pipeline was not even started
    STATUS_IN_PROGRESS = "IN PROGRESS"  # pipeline is executing
    STATUS_SUCCESS = "SUCCESS"  # pipeline executed with status SUCCESS
    STATUS_UNSTABLE = "UNSTABLE"  # pipeline executed with status UNSTABLE
    STATUS_FAILED = "FAILED"  # pipeline failed during the execution
    STATUS_ABORTED = "ABORTED"  # pipeline execution was aborted
    STATUS_MANUAL = "MANUAL" # git pipeline manual status

    STATUSES_SUPPORTED = [STATUS_UNKNOWN, STATUS_TIMEOUT, STATUS_NOT_STARTED, STATUS_IN_PROGRESS, STATUS_SUCCESS,
                          STATUS_UNSTABLE, STATUS_FAILED, STATUS_ABORTED, STATUS_MANUAL]
    STATUSES_COMPLETE = [STATUS_SUCCESS, STATUS_UNSTABLE, STATUS_FAILED, STATUS_ABORTED]

    def __init__(self):
        self.url = ""  # url to pipeline execution
        self.id = ""  # unique id of the execution
        self.status = ExecutionInfo.STATUS_UNKNOWN  # current status of the pipeline
        self.time_start = datetime.now()  # datetime when pipeline is started
        self.time_stop = self.time_start  # datetime when pipeline is finished
        self.name = ""  # optional name of the pipeline
        self.params = {}  # optional params used to run the pipe

    def start(self):
        self.time_start = datetime.now()
        self.status = ExecutionInfo.STATUS_IN_PROGRESS
        return self

    def stop(self, status: str):
        self.with_status(status)
        self.time_stop = datetime.now()
        return self

    def get_url(self):
        return self.url

    def get_id(self):
        return self.id

    def get_status(self):
        return self.status

    def get_time_start(self):
        return self.time_start

    def get_time_stop(self):
        return self.time_stop

    def get_duration(self):
        return self.time_stop - self.time_start
    
    def get_duration_str(self):
        seconds = int(self.get_duration().total_seconds())
        parts = [seconds / 3600, (seconds % 3600) / 60, seconds % 60]
        strings = list(map(lambda x: str(int(x)).zfill(2), parts))
        return ":".join(strings)

    def get_name(self):
        return self.name

    def get_params(self):
        return self.params

    def with_url(self, url: str):
        self.url = url
        return self

    def with_id(self, id):
        self.id = id
        return self

    def with_status(self, status: str):
        if status not in ExecutionInfo.STATUSES_SUPPORTED:
            raise Exception(f"Status {status} is not supported")
        self.status = status
        return self

    def with_name(self, name: str):
        self.name = name
        return self

    def with_params(self, params: dict):
        self.params = params
        return self
