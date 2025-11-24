import logging, sys, os
from qubership_pipelines_common_library.v2.utils.file_utils import FileUtils

logging.basicConfig(level=logging.INFO, stream=sys.stdout)


if __name__ == '__main__':
    exec_dir = 'x_devtest_dir'
    os.chdir("..")
    FileUtils.create_exec_dir(exec_dir)
    try:
        from qubership_pipelines_common_library.v2.podman.podman_command import PodmanRunImage
        cmd = PodmanRunImage(folder_path=exec_dir, input_params={
            "params": {
                "image": "docker.io/library/hello-world:latest",
                "execution_config": {
                    "additional_run_flags": "--cgroups=disabled2222",
                }
            }
        })
        cmd.run()
    except Exception as e:
        print(e)

