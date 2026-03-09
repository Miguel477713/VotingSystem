import os
import socket
import threading
import sys
from typing import Tuple

from VoteRepository.SqlServer.SqlVoteRepository import SqlVoteRepository
from VoteRepository.VoteRepositoryBase import VoteRepositoryBase


host = "0.0.0.0" #all network interfaces
port = 5050

options = ["A", "B", "C"]

voteRepository: VoteRepositoryBase | None = None


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


def HandleClient(connection: socket.socket, address) -> None:
    global voteRepository

    userId = None
    bufferData = bytearray()

    try:
        SendLine(connection, "OK Welcome. Use: HELLO <userId>")

        while True:
            line, bufferData = ReceiveLine(connection, bufferData)

            if line is None:
                if userId is not None:
                    voteRepository.Audit("DISCONNECT", userId=userId, details=f"addr={address}")
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
                voteRepository.Audit("LOGIN", userId=userId, details=f"addr={address}")
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

                accepted, reason = voteRepository.TryRecordVote(userId, option)
                if not accepted:
                    SendLine(connection, f"ERR {reason}")
                    continue

                SendLine(connection, "OK vote_recorded")

            elif command == "RESULTS":
                SendLine(connection, voteRepository.GetSnapshotResults())
                if userId is not None:
                    voteRepository.Audit("RESULTS", userId=userId)

            elif command == "PING":
                SendLine(connection, "OK pong")

            elif command == "QUIT":
                SendLine(connection, "OK bye")
                if userId is not None:
                    voteRepository.Audit("QUIT", userId=userId)
                break

            else:
                SendLine(connection, "ERR unknown_command")

    finally:
        try:
            connection.close()
        except Exception:
            pass


def Main() -> None:
    global port, voteRepository

    if len(sys.argv) >= 2:
        port = int(sys.argv[1])

    connectionString = os.environ["VOTING_SQL_CONNECTION_STRING"]

    createdRepository = SqlVoteRepository(options=options, connectionString=connectionString)

    if not isinstance(createdRepository, VoteRepositoryBase):
        raise TypeError("Repository does not implement VoteRepositoryBase contract")

    voteRepository = createdRepository
    voteRepository.Audit("SERVER_START", details=f"host={host} port={port} options={options}")

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
