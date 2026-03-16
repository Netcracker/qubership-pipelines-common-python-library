import copy
import pytest

from pathlib import Path
from unittest.mock import patch, MagicMock
from qubership_pipelines_common_library.v2.pipelines.prepare_pyz_module_command import PreparePyzModule


class TestPreparePyzModule:

    REQUIRED_INPUT_PARAMS = {
        'params': {
            'target_path': 'module_cli',
            'direct_url': 'https://qubership.org/test-target-url',
            'artifact_finder': {
                'artifact_id': 'light_cli',
                'version': '1.0.0-RELEASE'
            }
        }
    }

    @staticmethod
    def create_sample_zip():
        import io, zipfile
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
            zip_file.writestr('module/__init__.py', '# test module')
            zip_file.writestr('module/main.py', 'print("Hello")')
        zip_buffer.seek(0)
        return zip_buffer.read()

    def test_prepare_pyz_fails_without_mandatory_params(self, caplog, tmp_path):
        with pytest.raises(SystemExit) as exit_result:
            cmd = PreparePyzModule(folder_path=str(tmp_path))
            cmd.run()

        assert exit_result.value.code == 1
        assert "Parameter 'params.target_path' is mandatory" in caplog.text

    @patch('requests.sessions.Session.get')
    def test_prepare_pyz_direct_download(self, session_get, tmp_path):
        input_params = copy.deepcopy(self.REQUIRED_INPUT_PARAMS)
        input_params['params']['target_path'] = Path(tmp_path).joinpath("module_cli").as_posix()
        input_params['systems'] = {'http': {'headers_auth': {'Authorization': 'Bearer SOME_TOKEN'}}}

        get_response = MagicMock()
        get_response.iter_content.return_value = [TestPreparePyzModule.create_sample_zip()]
        session_get.return_value = get_response

        with pytest.raises(SystemExit) as exit_result:
            cmd = PreparePyzModule(folder_path=str(tmp_path), input_params=input_params)
            cmd.run()

        assert exit_result.value.code == 0
        assert cmd.session is not None
        assert cmd.session.headers["Authorization"] == "Bearer SOME_TOKEN"

    @patch('requests.sessions.Session.get')
    @patch('qubership_pipelines_common_library.v2.artifacts_finder.providers.nexus.NexusProvider.search_artifacts')
    def test_prepare_pyz_find_artifact(self, nexus_search, session_get, tmp_path):
        input_params = copy.deepcopy(self.REQUIRED_INPUT_PARAMS)
        input_params['params']['target_path'] = Path(tmp_path).joinpath("module_cli").as_posix()
        input_params['systems'] = {"artifact_finder":{"nexus": {"registry_url": "some_nexus_url"}}}

        nexus_search.return_value = ["test_resource_url"]
        get_response = MagicMock()
        get_response.content = TestPreparePyzModule.create_sample_zip()
        session_get.return_value = get_response

        with pytest.raises(SystemExit) as exit_result:
            cmd = PreparePyzModule(folder_path=str(tmp_path), input_params=input_params)
            cmd.run()

        assert exit_result.value.code == 0
        assert cmd.artifact_finder is not None
