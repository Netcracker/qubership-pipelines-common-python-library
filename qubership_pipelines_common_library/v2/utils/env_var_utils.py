import os


class EnvVarUtils:

    @staticmethod
    def get_from_env_or_file(base_name: str) -> str | None:
        """
        Resolves environment variable's value:

        1. Direct environment variable: `base_name`
        2. Indirect environment variable: `${base_name}_ENV` names another variable to read
        3. File-based: `${base_name}_FILE` points to a file whose contents are returned

        Returns `None` if none of the sources are available.
        """
        if value := os.getenv(base_name):
            return value

        if var_name := os.getenv(f"{base_name}_ENV"):
            if value := os.getenv(var_name):
                return value

        if file_path := os.getenv(f"{base_name}_FILE"):
            with open(file_path) as f:
                content = f.read().strip()
                if content:
                    return content

        return None
