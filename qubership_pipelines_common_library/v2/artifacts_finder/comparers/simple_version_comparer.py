import re

from qubership_pipelines_common_library.v2.artifacts_finder.model.comparer import Comparer


class SimpleVersionComparer(Comparer):
    """Orders versions by their embedded SEMVER triplet, then by snapshot timestamp/build number, then by the raw string as a final tie-breaker."""

    def compare(self, v1: str, v2: str) -> int:
        k1, k2 = self._sort_key(v1), self._sort_key(v2)
        if k1 < k2:
            return -1
        if k1 > k2:
            return 1
        return 0

    @staticmethod
    def _sort_key(version: str):
        semver = re.search(r'(\d+)\.(\d+)\.(\d+)', version)
        semver_key = tuple(int(part) for part in semver.groups()) if semver else (-1, -1, -1)
        timestamp = re.search(r'(\d{8})\.(\d{6})(?:-(\d+))?', version)
        timestamp_key = (int(timestamp.group(1)), int(timestamp.group(2)), int(timestamp.group(3) or 0)) if timestamp else (-1, -1, -1)
        return semver_key, timestamp_key, version
