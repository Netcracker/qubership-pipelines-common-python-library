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

import logging, os, re, shutil
from pathlib import Path
from git import Repo

from qubership_pipelines_common_library.v1.utils.utils_file import UtilsFile


class GitClient:

    def __init__(self, host: str, username: str, password: str, email: str = None):
        """
        Arguments:
            host (str): Git instance URL
            username (str): User used in auth request
            password (str): Token used in auth request
            email (str): Email used when committing changes using client
        """
        self.host = host.rstrip("/")
        self.username = username
        self.email = email
        self.password = password
        self.temp_path = None  # path to temporary folder to process files
        self.repo = None  # git repository object
        self.repo_path = None  # path to repository in GIT
        self.branch = None  # last processed branch
        logging.info("Git Client configured for %s", self.host)

    def clone(self, repo_path: str, branch: str, temp_path: str, **kwargs):
        """"""
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
            **kwargs
        )

    def clone_repo_from_commit_hash(self, repo_path: str, commit_hash: str, temp_path: str):
        """"""
        repo_path = repo_path.lstrip("/").rstrip("/")
        if not repo_path:
            raise Exception("Repository path should be defined")
        if not commit_hash:
            raise Exception("Commit hash should be defined")
        if not temp_path:
            raise Exception("Temporary path should be defined")
        self._cleanup_resources()
        self.repo_path = repo_path
        self.temp_path = temp_path
        self.repo = Repo.init(path=temp_path)
        self.repo.create_remote(name="origin", url=self._gen_repo_auth_url(self.host, self.username, self.password, self.repo_path))
        self.repo.git.fetch("--depth", "1", "origin", commit_hash)
        self.repo.git.checkout("FETCH_HEAD")

    def commit_and_push(self, commit_message: str):
        """"""
        self.commit(commit_message)
        self.push()

    def commit(self, commit_message: str):
        """"""
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

    def push(self):
        """"""
        if not self._is_cloned():
            raise Exception("Cannot push without preliminary cloning")
        logging.debug(f"Push into remote = {self.repo.remote().name} and branch = {self.repo.active_branch.name}")
        self.repo.git.push(self.repo.remote().name, self.repo.active_branch.name)

    def pull(self, **kwargs):
        """"""
        if not self._is_cloned():
            raise Exception("Cannot pull without preliminary cloning")
        logging.debug(f"Pull with options: {kwargs}")
        self.repo.git.pull(**kwargs)

    def get_file_content_utf8(self, relative_path: str):
        """"""
        if not self._is_cloned():
            raise Exception("Cannot get file content without preliminary cloning")
        filepath = os.path.join(self.temp_path, relative_path)
        return UtilsFile.read_text_utf8(filepath)

    def set_file_content_utf8(self, relative_path: str, content: str):
        """"""
        if not self._is_cloned():
            raise Exception("Cannot set file content without preliminary cloning")
        filepath = os.path.join(self.temp_path, relative_path)
        UtilsFile.write_text_utf8(filepath, content)

    def delete_by_path(self, relative_path: str):
        """"""
        if not self._is_cloned():
            raise Exception("Cannot delete file without preliminary cloning")
        filepath = os.path.join(self.temp_path, relative_path)
        if Path(filepath).is_file():
            Path(filepath).unlink()
        elif Path(filepath).is_dir():
            shutil.rmtree(filepath)

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
