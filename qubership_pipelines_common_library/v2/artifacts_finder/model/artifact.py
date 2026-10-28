import re


class Artifact:

    TIMESTAMP_VERSION_PATTERN = "^(.*-)([0-9]{8}\\.[0-9]{6}-([0-9]+))$"
    _TIMESTAMP_VERSION_RE = re.compile(TIMESTAMP_VERSION_PATTERN)

    def __init__(self, group_id = None, artifact_id = None, version = None, extension='jar'):
        self.group_id = group_id
        self.artifact_id = artifact_id
        self.version = version
        self.extension = "jar" if not extension else extension

    def is_snapshot(self):
        return self.version and self.version.endswith("-SNAPSHOT")

    def has_version_wildcard(self):
        return self.version and "*" in self.version

    def is_timestamped_snapshot(self) -> bool:
        return self.parse_timestamped_version(self.version) is not None

    def snapshot_base_version(self) -> str | None:
        """Return the base version for `X-SNAPSHOT` and timestamped snapshot versions, or None for any other version."""
        if not self.version:
            return None
        if self.version.endswith("-SNAPSHOT"):
            return self.version.removesuffix("-SNAPSHOT")
        parsed_version = self.parse_timestamped_version(self.version)
        return parsed_version[0] if parsed_version else None

    @staticmethod
    def parse_timestamped_version(version: str | None) -> tuple[str, str, int] | None:
        """Return the base version, timestamp-build, and build number of a timestamped snapshot version, or None."""
        match = Artifact._TIMESTAMP_VERSION_RE.fullmatch(version) if version else None
        if not match:
            return None
        return match.group(1)[:-1], match.group(2), int(match.group(3))

    def get_filename(self) -> str:
        return f"{self.artifact_id}-{self.version}.{self.extension}"

    @staticmethod
    def from_string(artifact_str: str):
        parts = artifact_str.split(":")
        if len(parts) == 3:
            group, artifact, version = parts[0], parts[1], parts[-1]
            return Artifact(group, artifact, version)
        raise Exception("Invalid artifact string")
