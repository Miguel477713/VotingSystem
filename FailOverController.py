import socket
import subprocess
import time
from typing import Optional
import sys


PRIMARY_HOST = "169.254.236.19"
PRIMARY_PORT = 5050

SECONDARY_SERVICE = "voting-tcp.service"  # systemd unit

CHECK_INTERVAL_SECONDS = 1.0
CONNECT_TIMEOUT_SECONDS = 0.8


def IsPrimaryReachable(host: str, port: int, timeoutSeconds: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeoutSeconds):
            return True
    except OSError:
        return False


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
    global PRIMARY_HOST, PRIMARY_PORT

    # Optional args for single-machine simulation:
    if len(sys.argv) >= 2:
        PRIMARY_PORT = int(sys.argv[1])
    if len(sys.argv) >= 3:
        PRIMARY_HOST = sys.argv[2]
    lastAction: Optional[str] = None

    while True:
        primaryUp = IsPrimaryReachable(PRIMARY_HOST, PRIMARY_PORT, CONNECT_TIMEOUT_SECONDS)

        if primaryUp:
            # Primary reachable: ensure standby is stopped
            if IsServiceActive(SECONDARY_SERVICE):
                StopService(SECONDARY_SERVICE)
                lastAction = "stopped-secondary"
                print("[failover] primary reachable -> stopping secondary")
            else:
                if lastAction != "secondary-already-stopped":
                    print("[failover] primary reachable -> secondary already stopped")
                    lastAction = "secondary-already-stopped"
        else:
            # Primary unreachable: ensure standby is started
            if not IsServiceActive(SECONDARY_SERVICE):
                StartService(SECONDARY_SERVICE)
                lastAction = "started-secondary"
                print("[failover] primary unreachable -> starting secondary")
            else:
                if lastAction != "secondary-already-running":
                    print("[failover] primary unreachable -> secondary already running")
                    lastAction = "secondary-already-running"

        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    Main()