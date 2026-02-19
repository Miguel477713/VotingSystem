import socket
import threading
import time
import sys
from typing import Dict, Set, Tuple
import os

host = "0.0.0.0" #all network interfaces
port = 5050

options = ["A", "B", "C"]
auditLogFile = "audit.log"

votes: Dict[str, int] = {option: 0 for option in options}
votedUsers: Set[str] = set()

stateLock = threading.Lock()
logLock = threading.Lock()



def Audit(event: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} {event}\n"
    #with is equivalent to:
    #logLock.acquire()
    #try:
        # critical section
    #finally:
    #    logLock.release()
    with logLock:
        with open(auditLogFile, "a", encoding="utf-8") as file:
            file.write(line)


def SendLine(connection: socket.socket, message: str) -> None:
    connection.sendall((message + "\n").encode("utf-8"))


def ReceiveLine(connection: socket.socket, bufferData: bytearray) -> Tuple[str | None, bytearray]:
    while True:#data arrives in pieces
        newlineIndex = bufferData.find(b"\n")
        if newlineIndex != -1:
            line = bufferData[:newlineIndex].decode("utf-8", errors="replace").rstrip("\r")
            bufferData = bufferData[newlineIndex + 1:]
            #line: command at a time delimited by \n
            #bufferData: unprocessed stream \n
            return line, bufferData 

        data = connection.recv(4096) #4096 as byte limit, Blocking state
        if not data:
            return None, bufferData
        bufferData.extend(data)


def SnapshotResults() -> str:
    with stateLock:
        parts = [f"{option}={votes.get(option, 0)}" for option in options]
    return "RESULTS " + " ".join(parts)


def HandleClient(connection: socket.socket, address) -> None:
    userId = None
    bufferData = bytearray()

    try:
        SendLine(connection, "OK Welcome. Use: HELLO <userId>")

        while True:
            line, bufferData = ReceiveLine(connection, bufferData)

            if line is None:
                if userId is not None:
                    Audit(f"DISCONNECT user={userId} addr={address}")
                break

            line = line.strip()
            if not line:
                continue

            parts = line.split()
            command = parts[0].upper()

            if command == "HELLO":
                if len(parts) != 2:
                    SendLine(connection, "ERR usage: HELLO <userId>")
                    continue

                userId = parts[1]
                Audit(f"LOGIN user={userId} addr={address}")
                SendLine(connection, f"OK Hello {userId}. Options: {','.join(options)}")

            elif command == "VOTE":
                if userId is None:
                    SendLine(connection, "ERR must_login_first")
                    continue

                if len(parts) != 2:
                    SendLine(connection, "ERR usage: VOTE <option>")
                    continue

                option = parts[1].upper()

                if option not in options:
                    SendLine(connection, "ERR invalid_option")
                    continue

                with stateLock:
                    if userId in votedUsers:
                        SendLine(connection, "ERR already_voted")
                        Audit(f"VOTE_REJECT user={userId} reason=already_voted")
                        continue

                    votedUsers.add(userId)
                    votes[option] += 1

                Audit(f"VOTE_ACCEPT user={userId} option={option}")
                SendLine(connection, "OK vote_recorded")

            elif command == "RESULTS":
                SendLine(connection, SnapshotResults())
                if userId is not None:
                    Audit(f"RESULTS user={userId}")

            elif command == "PING":
                SendLine(connection, "OK pong")

            elif command == "QUIT":
                SendLine(connection, "OK bye")
                if userId is not None:
                    Audit(f"QUIT user={userId}")
                break

            else:
                SendLine(connection, "ERR unknown_command")

    except ConnectionResetError:
        if userId is not None:
            Audit(f"DISCONNECT_RESET user={userId} addr={address}")
    except Exception as exception:
        Audit(f"SERVER_ERROR addr={address} err={type(exception).__name__}:{exception}")
    finally:
        try:
            connection.close()
        except Exception:
            pass

def LoadLog():
    """Reads the log file to restore the votes on the memory"""
    global votes, votedUsers
    if not os.path.exists(auditLogFile):
        return

    print(f"[storage] Loading log from {auditLogFile}...")
    try:
        with open(auditLogFile, "r", encoding="utf-8") as f:
            for line in f:
                # We search for lines that say VOTE_ACCEPT
                if "VOTE_ACCEPT" in line:
                    parts = line.strip().split()
                    user = None
                    option = None
                    for part in parts:
                        if part.startswith("user="):
                            user = part.split("=")[1]
                        elif part.startswith("option="):
                            option = part.split("=")[1]

                    # We rebuild the memory state
                    if user and option and user not in votedUsers:
                        votedUsers.add(user)
                        votes[option] += 1
        print(f"[storage] Restored state: {votes}")
    except Exception as e:
        print(f"[storage] Error reading log: {e}")

def Main() -> None:
    global port, auditLogFile

    # Optional args for single-machine simulation:
    #   python Server.py [port] [auditLogFile]
    if len(sys.argv) >= 2:
        port = int(sys.argv[1])
    if len(sys.argv) >= 3:
        auditLogFile = sys.argv[2]

    LoadLog()

    Audit(f"SERVER_START host={host} port={port} options={options}")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as serverSocket:
        serverSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)#interminence 
        serverSocket.bind((host, port))
        serverSocket.listen(50) #waiting clients in queue

        print(f"[server] Listening on {host}:{port} options={options}")

        while True:
            #connection: new socket, not the listener serverSocket
            #address: public ip and port of client 
            connection, address = serverSocket.accept()
            thread = threading.Thread( #after thread, loop goes back to waiting for an accept
                target=HandleClient,
                args=(connection, address),
                daemon=True #terminate threads with script
            )
            thread.start()


if __name__ == "__main__":
    Main()
