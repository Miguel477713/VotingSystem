from abc import ABC, abstractmethod
from typing import Tuple

class VoteRepositoryBase(ABC):
    @abstractmethod
    def Audit(self, event: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def LoadLog(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def SnapshotResults(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def TryRecordVote(self, userId: str, option: str) -> Tuple[bool, str]:
        raise NotImplementedError