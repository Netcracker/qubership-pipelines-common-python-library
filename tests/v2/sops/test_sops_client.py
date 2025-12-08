import os
import sys
import shutil
import stat
import unittest
import pytest
import requests
import yaml

from pathlib import Path
from qubership_pipelines_common_library.v1.utils.utils_dictionary import UtilsDictionary
from qubership_pipelines_common_library.v2.sops.sops_client import SopsClient


@pytest.mark.skipif(sys.platform != "linux", reason="Test SOPS with Linux binaries only")
class TestSopsClient(unittest.TestCase):

    DEFAULT_SOPS_ARTIFACT_LOCATION_URL = "https://github.com/getsops/sops/releases/download/v3.10.2/sops-v3.10.2.linux.amd64"

    TEMP_FOLDER = Path("tests/v2/sops/data/temp")
    ENCRYPTED_FILE_PATH = TEMP_FOLDER.joinpath("generated-file-secure.yaml")
    SOURCE_FILE_PATH_TO_ENCRYPT = Path("tests/v2/sops/data/generated-file-secure.yaml")

    @classmethod
    def setUpClass(cls):
        temp_folder = cls.TEMP_FOLDER
        if temp_folder.exists() and temp_folder.is_dir():
            shutil.rmtree(temp_folder)
        os.makedirs(temp_folder)
        sops_artifact_path = Path(temp_folder, "sops")
        if not sops_artifact_path.exists():
            cls.download_sops_artifact(sops_artifact_path)
        os.environ["SOPS_EXECUTABLE"] = str(sops_artifact_path)

    @classmethod
    def download_sops_artifact(cls, sops_artifact_path):
        response = requests.get(cls.DEFAULT_SOPS_ARTIFACT_LOCATION_URL)
        with open(sops_artifact_path, mode="wb") as file:
            file.write(response.content)

        os_stat = os.stat(sops_artifact_path)
        os.chmod(sops_artifact_path, os_stat.st_mode | stat.S_IEXEC)

    def test_sops_encrypt__save_result_into_different_file(self):
        # given
        age_public_key = "age1gryqvlh4zq7tl8qgfsuc0pla5yv04ypclg73m8mwpfjaa0vvmurq6536ws"
        sops_client = SopsClient(self.TEMP_FOLDER)
        # when
        sops_client.encrypt_content_by_path(age_public_key, self.SOURCE_FILE_PATH_TO_ENCRYPT, self.ENCRYPTED_FILE_PATH)
        # then
        with open(self.ENCRYPTED_FILE_PATH, mode="r") as file:
            actual_encrypted_content = yaml.safe_load(file)

        self.assertEqual(1, len(actual_encrypted_content['sops']['age']))
        self.assertEqual(age_public_key, actual_encrypted_content['sops']['age'][0]['recipient'])
        self.assertTrue(actual_encrypted_content['sops']['age'][0]['enc'])

    def test_sops_encrypt__save_result_into_same_file(self):
        # given
        age_public_key = "age1gryqvlh4zq7tl8qgfsuc0pla5yv04ypclg73m8mwpfjaa0vvmurq6536ws"
        sops_client = SopsClient(self.TEMP_FOLDER)
        shutil.copyfile(self.SOURCE_FILE_PATH_TO_ENCRYPT, self.ENCRYPTED_FILE_PATH)
        # when
        sops_client.encrypt_content_by_path(age_public_key, self.ENCRYPTED_FILE_PATH)
        # then
        with open(self.ENCRYPTED_FILE_PATH, mode="r") as file:
            actual_encrypted_content = yaml.safe_load(file)

        self.assertEqual(1, len(actual_encrypted_content['sops']['age']))
        self.assertEqual(age_public_key, actual_encrypted_content['sops']['age'][0]['recipient'])
        self.assertTrue(actual_encrypted_content['sops']['age'][0]['enc'])

    def test_sops_decrypt(self):
        # given
        age_private_key = "AGE-SECRET-KEY-1SHXCVUX3RWY7HTCRZYJ2CCMH7XVFQT2K509JR59JFR4EQRY66D7S4H70YM"
        age_public_key = "age1gryqvlh4zq7tl8qgfsuc0pla5yv04ypclg73m8mwpfjaa0vvmurq6536ws"
        sops_client = SopsClient(self.TEMP_FOLDER)
        sops_client.encrypt_content_by_path(age_public_key, self.SOURCE_FILE_PATH_TO_ENCRYPT, self.ENCRYPTED_FILE_PATH)
        # when
        actual_decrypted_content = sops_client.get_decrypted_content_by_path(
            age_private_key, Path(self.ENCRYPTED_FILE_PATH))
        # then
        actual_decrypted_content_yaml = yaml.safe_load(actual_decrypted_content)
        self.assertEqual("admin",
                         UtilsDictionary.get_by_path(actual_decrypted_content_yaml, "systems.registry.password", ""))
        self.assertEqual("token1",
                         UtilsDictionary.get_by_path(actual_decrypted_content_yaml,
                                                     "common.environment.namespaces.dev-3-core.k8s_token", ""))

    def test_sops_decrypt_non_encrypted_file__should_return_empty_string(self):
        # given
        age_private_key = "AGE-SECRET-KEY-1SHXCVUX3RWY7HTCRZYJ2CCMH7XVFQT2K509JR59JFR4EQRY66D7S4H70YM"
        sops_client = SopsClient(self.TEMP_FOLDER)
        # when
        actual_decrypted_content = sops_client.get_decrypted_content_by_path(
            age_private_key, self.SOURCE_FILE_PATH_TO_ENCRYPT)
        # then
        self.assertEqual("", actual_decrypted_content)


if __name__ == "__main__":
    unittest.main()
