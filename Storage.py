from typing import Dict, Set
import os


class FileVoteStorage(VoteStorage):
    def __init__(self, logFile: str, options: list[str]):
        self.logFile = logFile
        self.options = options

    def LoadState(self) -> tuple[Dict[str, int], Set[str]]:
        votesLocal: Dict[str, int] = {option: 0 for option in options}
        votedUsersLocal: Set[str] = set()

        if not os.path.exists(self.logFile):
            return votesLocal, votedUsersLocal

        print(f"[storage] Loading log from {self.logFile}...")

        try:
            with open(self.logFile, "r", encoding="utf-8") as f:
                for line in f:
                    if "VOTE_ACCEPT" in line:
                        parts = line.strip().split()
                        user = None
                        option = None

                        for part in parts:
                            if part.startswith("user="):
                                user = part.split("=")[1]
                            elif part.startswith("option="):
                                option = part.split("=")[1]

                        if user and option and user not in votedUsersLocal:
                            votedUsersLocal.add(user)
                            votesLocal[option] += 1

        except Exception as e:
            print(f"[storage] Error reading log: {e}")

        print(f"[storage] Restored state: {votesLocal}")
        return votesLocal, votedUsersLocal