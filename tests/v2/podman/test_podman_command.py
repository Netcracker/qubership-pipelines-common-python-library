import pytest
from qubership_pipelines_common_library.v2.podman.podman_command import PodmanRunImage


class TestPodmanRunImage:

    def test_podman_run_fails_without_image(self, caplog, tmp_path):
        with pytest.raises(SystemExit) as exit_result:
            cmd = PodmanRunImage(folder_path=str(tmp_path))
            cmd.run()

        assert exit_result.value.code == 1
        assert "Parameter 'params.image' is mandatory" in caplog.text

    def test_podman_run_fails_without_binaries(self, caplog, tmp_path):
        with pytest.raises(SystemExit) as exit_result:
            cmd = PodmanRunImage(folder_path=str(tmp_path), input_params={'params': {'image': 'qubership_non_existent_image:latest'}})
            cmd.run()

        assert exit_result.value.code == 1
        assert "StatusCode: 404" in caplog.text
