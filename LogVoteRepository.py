import threading
import time
import os
from typing import Dict, Set, Tuple, List

from VoteRepositoryBase import VoteRepositoryBase


class LogVoteRepository(VoteRepositoryBase):
    def __init__(self, options: List[str], auditLogFile: str) -> None:
        self.options = options
        self.auditLogFile = auditLogFile

        self.votes: Dict[str, int] = {option: 0 for option in self.options}
        self.votedUsers: Set[str] = set()

        self.stateLock = threading.Lock()
        self.logLock = threading.Lock()

        self.LoadLog()

    def Audit(self, event: str) -> None:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"{timestamp} {event}\n"

        #with is equivalent to:
        #logLock.acquire()
        #try:
            # critical section
        #finally:
        #    logLock.release()
        with self.logLock:
            with open(self.auditLogFile, "a", encoding="utf-8") as file:
                file.write(line)

    def LoadLog(self) -> None:
        """
        Restore server state by replaying the audit log file.

        This function reads the audit log and reconstructs the voting state
        (votes and votedUsers) from previously recorded VOTE_ACCEPT events.
        This provides persistence across server restarts.
        """
        if not os.path.exists(self.auditLogFile):
            return

        print(f"[storage] Loading log from {self.auditLogFile}...")

        try:
            votesFromLog: Dict[str, int] = {option: 0 for option in self.options}
            votedUsersFromLog: Set[str] = set()

            with open(self.auditLogFile, "r", encoding="utf-8") as file:
                for line in file:
                    if "VOTE_ACCEPT" not in line:
                        continue

                    parts = line.strip().split()
                    userId = None
                    option = None

                    for part in parts:
                        if part.startswith("user="):
                            userId = part.split("=", 1)[1]
                        elif part.startswith("option="):
                            option = part.split("=", 1)[1]

                    if userId is None or option is None:
                        continue
                    if option not in votesFromLog:
                        continue
                    if userId in votedUsersFromLog:
                        continue

                    votedUsersFromLog.add(userId)
                    votesFromLog[option] += 1

            with self.stateLock:
                self.votes = votesFromLog
                self.votedUsers = votedUsersFromLog

            print(f"[storage] Restored state: {self.votes}")

        except Exception as exception:
            print(f"[storage] Error reading log: {exception}")

    def SnapshotResults(self) -> str:
        with self.stateLock:
            parts = [f"{option}={self.votes.get(option, 0)}" for option in self.options]
        return "RESULTS " + " ".join(parts)

    def TryRecordVote(self, userId: str, option: str) -> Tuple[bool, str]:
        """
        Returns:
            (True, "vote_recorded") when the vote is accepted
            (False, "already_voted") when the user voted before
        """
        with self.stateLock:
            if userId in self.votedUsers:
                return False, "already_voted"

            self.votedUsers.add(userId)
            self.votes[option] += 1

        self.Audit(f"VOTE_ACCEPT user={userId} option={option}")
        return True, "vote_recorded"
