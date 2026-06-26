import re
from dataclasses import dataclass
from typing import Literal

from qubership_pipelines_common_library.v2.artifacts_finder.model.comparer import Comparer

CompareResult = Literal[-2, -1, 0, 1, 2]

# Matches the first occurrence of MAJOR.MINOR.PATCH anywhere in a string.
# Negative look-around prevents matching sub-sequences of longer dotted
# numbers such as "1.2.3.4".
_SEMVER_RE = re.compile(r"(?<!\d)(\d+)\.(\d+)\.(\d+)(?!\.\d)")


class DefaultVersionComparer(Comparer):
    def __init__(self):
        self._delegate = VersionComparer()

    def compare(self, v1: str, v2: str) -> int:
        return self._delegate.compare(v1, v2)


@dataclass(frozen=True)
class _ParsedVersion:
    prefix: str
    semver: tuple[int, int, int]
    suffix: str


class VersionComparer:
    def compare(self, v1: str, v2: str) -> CompareResult:
        """Compare two version strings.

        Returns:
            -2  if v1 < v2  and SEMVER major version differs (upgrade)
            -1  if v1 < v2  and SEMVER major is the same (or fallback lex)
             0  if v1 == v2
            +1  if v1 > v2  and SEMVER major is the same (or fallback lex)
            +2  if v1 > v2  and SEMVER major version differs (downgrade)

        Comparison strategy when both strings contain MAJOR.MINOR.PATCH:
            1. Compare the substrings *before* the SEMVER lexicographically.
            2. If equal, compare the SEMVER triplets (major diff - ±2, minor/patch diff - ±1).
            3. If equal, compare the substrings *after* the SEMVER lexicographically.

        If at least one string has no embedded SEMVER, fall back to a plain
        lexicographic comparison of the full strings.
        """
        v1, v2 = v1.strip(), v2.strip()

        p1 = self._parse(v1)
        p2 = self._parse(v2)

        if p1 is not None and p2 is not None:
            r = self._cmp(p1.prefix, p2.prefix)
            if r != 0:
                return r
            r = self._cmp_semver(p1.semver, p2.semver)
            if r != 0:
                return r
            return self._cmp(p1.suffix, p2.suffix)

        return self._cmp(v1, v2)

    def has_semver(self, version: str) -> bool:
        """Return True if *version* contains an embedded MAJOR.MINOR.PATCH."""
        return self._parse(version.strip()) is not None

    @staticmethod
    def _parse(version: str) -> _ParsedVersion | None:
        """Split *version* into (prefix, semver-triplet, suffix), or None."""
        m = _SEMVER_RE.search(version)
        if m is None:
            return None
        return _ParsedVersion(
            prefix=version[: m.start()],
            semver=(int(m.group(1)), int(m.group(2)), int(m.group(3))),
            suffix=version[m.end() :],
        )

    @staticmethod
    def _cmp_semver(
        parts1: tuple[int, int, int], parts2: tuple[int, int, int]
    ) -> CompareResult:
        """Compare two SEMVER triplets; major difference returns ±2."""
        maj1, min1, pat1 = parts1
        maj2, min2, pat2 = parts2
        if maj1 != maj2:
            return -2 if maj1 < maj2 else 2
        if (min1, pat1) < (min2, pat2):
            return -1
        if (min1, pat1) > (min2, pat2):
            return 1
        return 0

    @staticmethod
    def _cmp(a, b) -> CompareResult:
        """Generic three-way compare for any comparable type."""
        if a < b:
            return -1
        if a > b:
            return 1
        return 0
