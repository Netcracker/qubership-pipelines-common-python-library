from abc import ABC, abstractmethod


class Comparer(ABC):
    """Pluggable version-comparison interface used by ArtifactFinder to pick the 'latest' version.

    ``compare(v1, v2)`` must return:
        a negative number  if v1 sorts before v2 (v1 is older),
        0                  if v1 and v2 are considered equal,
        a positive number  if v1 sorts after  v2 (v1 is newer).
    Only the sign of the result is used; the magnitude is ignored.
    """

    @abstractmethod
    def compare(self, v1: str, v2: str) -> int:
        ...
