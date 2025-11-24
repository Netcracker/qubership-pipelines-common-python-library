from pathlib import Path


class FileUtils:

    @staticmethod
    def create_exec_dir(execution_folder_path: str | Path, exists_ok: bool = False) -> Path:
        import shutil
        exec_dir = Path(execution_folder_path)
        if exec_dir.exists() and not exists_ok:
            if exec_dir.is_dir():
                shutil.rmtree(exec_dir)
            else:
                raise FileExistsError(f"Path '{execution_folder_path}' exists and is a file, not a directory.")
        exec_dir.mkdir(parents=True, exist_ok=exists_ok)
        return exec_dir
