import logging
import os
import shutil
import subprocess
import uuid
import yaml

from pathlib import Path


class SopsClient:

    def __init__(self, sops_artifact_configs_folder_path: Path):
        self.sops_artifact_configs_folder_path = sops_artifact_configs_folder_path
        self.sops_executable = Path(os.environ.get("SOPS_EXECUTABLE", "/usr/local/bin/sops"))
        self.logger = logging.getLogger()

    def encrypt_content_by_path(
            self, age_public_key: str, source_file_path_to_encrypt: Path, target_file_path: Path = None):
        """
        Encrypts file and saves result into file by path
        Args:
            age_public_key: age public key
            source_file_path_to_encrypt: file to encrypt
            target_file_path: file to save result of encryption. If None then `source_file_path_to_encrypt` will be used
        """
        if not self.sops_executable.exists():
            self.logger.error(f"Sops executable doesn't exist. Can't encrypt file {source_file_path_to_encrypt}")
            return

        sops_config_path = self._get_prepared_sops_config_path(age_public_key)
        encrypted_file_path = target_file_path
        if not encrypted_file_path:
            encrypted_file_path = source_file_path_to_encrypt

        args = (self.sops_executable, "--config", sops_config_path, "encrypt", source_file_path_to_encrypt)
        sops_encrypt_result = subprocess.run(args, capture_output=True, text=True)
        if sops_encrypt_result.stderr:
            self.logger.error(f"Error during encryption of {source_file_path_to_encrypt}. "
                              f"Saving empty content into {encrypted_file_path}"
                              f"Error: {sops_encrypt_result.stderr}")

            with open(encrypted_file_path, 'w') as encrypted_file:
                encrypted_file.write("")
            self._remove_sops_config(sops_config_path.parent)
            return

        with open(encrypted_file_path, 'w') as encrypted_file:
            encrypted_file.write(sops_encrypt_result.stdout)
        self.logger.debug(f"Content {source_file_path_to_encrypt} was encrypted by sops. "
                          f"Result saved into {encrypted_file_path}")
        self._remove_sops_config(sops_config_path.parent)

    def get_decrypted_content_by_path(self, age_private_key: str, source_file_path_to_decrypt: Path) -> str:
        """
        Decrypts file by path
        Args:
            age_private_key: age private key
            source_file_path_to_decrypt: file path to decrypt

        Returns:
            decrypted file content or empty string if error occurs
        """
        if not self.sops_executable.exists():
            self.logger.error(f"Sops executable doesn't exist. Can't decrypt file {source_file_path_to_decrypt}")
            return ""
        if not age_private_key:
            self.logger.warning("sops_private_key is not defined, skipping decryption")
            return ""
        environment_variables = os.environ.copy()
        environment_variables["SOPS_AGE_KEY"] = age_private_key.strip()
        args = (self.sops_executable, "-d", source_file_path_to_decrypt)
        sops_decrypt_result = subprocess.run(args, env=environment_variables, capture_output=True, text=True)
        if sops_decrypt_result.stderr:
            self.logger.error(f"Error during {source_file_path_to_decrypt} decrypt. Error: {sops_decrypt_result.stderr}")
            return ""
        self.logger.debug(f"Content {source_file_path_to_decrypt} was decrypted by sops")
        return sops_decrypt_result.stdout

    def _get_prepared_sops_config_path(self, age_public_key) -> Path:
        """
        Generates `.sops.yaml` file `age-public-key`
        Creates folder `uuid.uuid4()` under `self.sops_artifact_configs_folder_path` to make `.sops.yaml`
        unique for exact encryption
        Args:
            age_public_key: age public key

        Returns:
            path to generated `.sops.yaml`
        """
        self.logger.debug("Preparing sops config for encryption")
        sops_config_content = {
            "creation_rules": [
                {
                    "age": age_public_key
                }
            ]
        }
        sops_config_path = self.sops_artifact_configs_folder_path.joinpath(str(uuid.uuid4()), ".sops.yaml")
        sops_config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(sops_config_path, mode="w") as file:
            yaml.dump(sops_config_content, file)
        return sops_config_path

    def _remove_sops_config(self, sops_config_folder: Path):
        """
        Removes folder with generated sops config
        Args:
            sops_config_folder: path to folder with sops config

        Returns:

        """
        self.logger.debug("Removing sops config")
        if sops_config_folder.exists() and sops_config_folder.is_dir():
            shutil.rmtree(sops_config_folder)
