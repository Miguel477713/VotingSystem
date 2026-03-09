import socket
import subprocess
import time
from typing import Optional
import sys
import os

from VoteRepository.SqlServer.SqlLeadershipService import SqlLeadershipService

SECONDARY_SERVICE = "voting-tcp.service"  # systemd unit

CHECK_INTERVAL_SECONDS = 3.0
LEASE_EXPIRE = 10

def RunSystemctl(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["systemctl"] + args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False
    )

def IsServiceActive(serviceName: str) -> bool:
    result = RunSystemctl(["is-active", serviceName])
    return result.returncode == 0 and result.stdout.strip() == "active"


def StartService(serviceName: str) -> None:
    RunSystemctl(["start", serviceName])


def StopService(serviceName: str) -> None:
    RunSystemctl(["stop", serviceName])


def Main() -> None:
    connectionString = os.environ["VOTING_SQL_CONNECTION_STRING"]
    hostName = socket.gethostname()

    leadershipService = SqlLeadershipService(connectionString=connectionString, resourceName="VotingLeader", 
                                             leaseSeconds=LEASE_EXPIRE)
    active = IsServiceActive(SECONDARY_SERVICE)

    while True:
        try:
            if active:
                renewed = leadershipService.RenewLeadership(hostName)

                if not renewed:
                    if IsServiceActive(SECONDARY_SERVICE):
                        StopService(SECONDARY_SERVICE)
                    active = False
            else:
                acquired = leadershipService.TryAcquireLeadership(hostName)

                if acquired:
                    if not IsServiceActive(SECONDARY_SERVICE):
                        StartService(SECONDARY_SERVICE)
                    active = True

            time.sleep(CHECK_INTERVAL_SECONDS)

        except Exception as error:
            print(f"[failover] error: {error}")
            time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    Main()