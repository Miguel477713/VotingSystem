# Import required modules for the TCP voting server
import socket  # For TCP socket connections
import threading  # For concurrent client handling
import time  # For timestamp generation
import sys  # For command line arguments
from typing import Dict, Set, Tuple  # For type hints
import os  # For file operations

# Server configuration
host = "0.0.0.0"  # Listen on all network interfaces
port = 5050       # TCP port for the voting server

# Voting system configuration
options = ["A", "B", "C"]  # Available voting options
auditLogFile = "audit.log"   # File for audit trail and persistence

# Global state variables (shared across all client connections)
votes: Dict[str, int] = {option: 0 for option in options}  # Vote counts for each option
votedUsers: Set[str] = set()  # Set of users who have already voted

# Thread synchronization locks
stateLock = threading.Lock()  # Protects access to votes and votedUsers
logLock = threading.Lock()    # Protects access to audit log file



def Audit(event: str) -> None:
    """
    Write an audit event to the log file with timestamp.
    
    This provides both an audit trail and persistence mechanism.
    The log can be replayed to restore server state after restart.
    
    Args:
        event: Description of the event to log
    """
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
    """
    Send a line of text over a socket connection.
    
    Args:
        connection: The socket to send data through
        message: The message string to send
    """
    # Add newline character and encode as UTF-8 bytes
    connection.sendall((message + "\n").encode("utf-8"))


def ReceiveLine(connection: socket.socket, bufferData: bytearray) -> Tuple[str | None, bytearray]:
    """
    Receive a line of text from a socket connection.
    Handles partial data reception and buffering.
    
    Args:
        connection: The socket to receive data from
        bufferData: Existing buffer data (may contain partial lines)
    
    Returns:
        Tuple containing:
        - The received line (without newline) or None if connection closed
        - Updated buffer data (remaining unprocessed data)
    """
    while True:
        # Look for newline character in buffer
        newlineIndex = bufferData.find(b"\n")
        if newlineIndex != -1:
            # Found complete line, extract it
            line = bufferData[:newlineIndex].decode("utf-8", errors="replace").rstrip("\r")
            # Remove the processed line from buffer
            bufferData = bufferData[newlineIndex + 1:]
            # Return the line and remaining buffer data
            return line, bufferData 

        # No complete line in buffer, receive more data
        data = connection.recv(4096)  # Receive up to 4096 bytes (blocking call)
        if not data:
            # Connection closed by client
            return None, bufferData
        bufferData.extend(data)  # Add received data to buffer


def SnapshotResults() -> str:
    """
    Generate a snapshot of current voting results.
    
    Returns:
        String containing current vote counts in format: "RESULTS A=0 B=0 C=0"
    """
    with stateLock:
        # Build result string with vote counts for each option
        parts = [f"{option}={votes.get(option, 0)}" for option in options]
    return "RESULTS " + " ".join(parts)


def HandleClient(connection: socket.socket, address) -> None:
    """
    Handle a single client connection throughout its lifetime.
    
    This function runs in a separate thread for each client and manages
    the complete client session from login to disconnect.
    
    Args:
        connection: Socket connection to the client
        address: Client's (IP, port) tuple
    """
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
    """
    Restore server state by replaying the audit log file.
    
    This function reads the audit log and reconstructs the voting state
    (votes and votedUsers) from previously recorded VOTE_ACCEPT events.
    This provides persistence across server restarts.
    """
    global votes, votedUsers  # Modify global variables
    
    # Check if log file exists
    if not os.path.exists(auditLogFile):
        return

    print(f"[storage] Loading log from {auditLogFile}...")
    try:
        with open(auditLogFile, "r", encoding="utf-8") as f:
            for line in f:
                # Look for accepted vote events
                if "VOTE_ACCEPT" in line:
                    # Parse the log line to extract user and option
                    parts = line.strip().split()
                    user = None
                    option = None
                    for part in parts:
                        if part.startswith("user="):
                            user = part.split("=")[1]
                        elif part.startswith("option="):
                            option = part.split("=")[1]

                    # Rebuild the in-memory state from log
                    if user and option and user not in votedUsers:
                        votedUsers.add(user)
                        votes[option] += 1
        print(f"[storage] Restored state: {votes}")
    except Exception as e:
        print(f"[storage] Error reading log: {e}")

def Main() -> None:
    """
    Main entry point for the TCP voting server.
    
    Starts the server, loads previous state, and begins accepting
    client connections in separate threads.
    """
    global port, auditLogFile  # Allow command line override

    # Parse optional command line arguments for testing:
    #   python Server.py [port] [auditLogFile]
    if len(sys.argv) >= 2:
        port = int(sys.argv[1])
    if len(sys.argv) >= 3:
        auditLogFile = sys.argv[2]

    # Restore previous state from audit log
    LoadLog()

    # Log server startup
    Audit(f"SERVER_START host={host} port={port} options={options}")

    # Create and configure the server socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as serverSocket:
        # Allow immediate socket reuse after server restart
        serverSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        serverSocket.bind((host, port))
        serverSocket.listen(50)  # Queue up to 50 waiting clients

        print(f"[server] Listening on {host}:{port} options={options}")

        # Main server loop - accept connections indefinitely
        while True:
            # Wait for new client connection
            # connection: new socket for this specific client
            # address: client's (IP, port) tuple
            connection, address = serverSocket.accept()
            
            # Create a new thread to handle this client
            thread = threading.Thread(
                target=HandleClient,
                args=(connection, address),
                daemon=True  # Thread will terminate when main script ends
            )
            thread.start()  # Start handling the client
            # Loop continues to wait for next connection


if __name__ == "__main__":
    Main()
