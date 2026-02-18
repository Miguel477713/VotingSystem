#!/usr/bin/env python3

import socket
import sys


def ReceiveLine(socketConnection: socket.socket) -> str | None:
    data = bytearray()
    while True:
        chunk = socketConnection.recv(1)
        if not chunk:
            return None
        if chunk == b"\n":
            return data.decode("utf-8", errors="replace").rstrip("\r")
        data.extend(chunk)


def SendLine(socketConnection: socket.socket, message: str) -> None:
    socketConnection.sendall((message + "\n").encode("utf-8"))


def Main() -> None:
    if len(sys.argv) != 4:
        print("Usage: python client.py <host> <port> <userId>")
        sys.exit(1)

    host = sys.argv[1]
    port = int(sys.argv[2])
    userId = sys.argv[3]

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as clientSocket:
        clientSocket.connect((host, port))

        line = ReceiveLine(clientSocket)
        if line is not None:
            print(line)

        SendLine(clientSocket, f"HELLO {userId}")
        print(ReceiveLine(clientSocket))

        print("Commands: vote <A|B|C>, results, ping, quit")

        while True:
            command = input("> ").strip()
            if not command:
                continue

            lowerCommand = command.lower()

            if lowerCommand.startswith("vote "):
                option = command.split(maxsplit=1)[1].strip()
                SendLine(clientSocket, f"VOTE {option}")

            elif lowerCommand == "results":
                SendLine(clientSocket, "RESULTS")

            elif lowerCommand == "ping":
                SendLine(clientSocket, "PING")

            elif lowerCommand == "quit":
                SendLine(clientSocket, "QUIT")

            else:
                print("Unknown. Use: vote <opt> | results | ping | quit")
                continue

            response = ReceiveLine(clientSocket)
            if response is None:
                print("[client] Disconnected")
                break

            print(response)

            if lowerCommand == "quit":
                break


if __name__ == "__main__":
    Main()
