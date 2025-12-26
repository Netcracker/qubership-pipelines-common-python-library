class Artifact:
    def __init__(self, group_id = None, artifact_id = None, version = None, extension='jar'):
        self.group_id = group_id
        self.artifact_id = artifact_id
        self.version = version
        self.extension = "jar" if not extension else extension

    def is_snapshot(self):
        return self.version and self.version.endswith("SNAPSHOT")

    def get_filename(self) -> str:
        return f"{self.artifact_id}-{self.version}.{self.extension}"

    @staticmethod
    def from_string(artifact_str: str):
        parts = artifact_str.split(":")
        if len(parts) == 3:
            group, artifact, version = parts[0], parts[1], parts[-1]
            return Artifact(group, artifact, version)
        raise Exception("Invalid artifact string")
