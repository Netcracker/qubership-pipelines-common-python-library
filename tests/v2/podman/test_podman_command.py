import pytest
from qubership_pipelines_common_library.v2.podman.podman_command import PodmanRunImage


class TestPodmanRunImage:

    def test_podman_run_fails_without_image(self, caplog):
        with pytest.raises(SystemExit) as exit_result:
            cmd = PodmanRunImage(folder_path='dynamic_test_context_dir')
            cmd.run()

        assert exit_result.value.code == 1
        assert "Parameter 'params.image' is mandatory" in caplog.text

    def test_podman_run_fails_without_binaries(self, caplog):
        with pytest.raises(SystemExit) as exit_result:
            cmd = PodmanRunImage(folder_path='dynamic_test_context_dir', input_params={'params':{'image':'qubership_non_existent_image:latest'}})
            cmd.run()

        assert exit_result.value.code == 1
        # Initially planned to test absence of 'podman', but GitHub runner does have it
        assert "StatusCode: 404" in caplog.text
