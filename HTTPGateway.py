# Import required modules for HTTP server functionality
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket  # For TCP socket connections
import urllib.parse  # For parsing URL-encoded form data
from typing import Tuple  # For type hints

# TCP backends configuration - primary server first, then fallback servers
# Format: (host, port) tuples
# The gateway will try each backend in order until one succeeds
tcpBackends = [
    ("20.120.242.3", 5050),  # Primary TCP backend server
    ("127.0.0.1", 5051),     # Fallback TCP backend server (localhost)
]

# HTTP server configuration
httpHost = "0.0.0.0"  # Listen on all network interfaces
httpPort = 8080       # HTTP port for the gateway


def TcpSendCommands(commands: list[str], timeoutSeconds: float = 3.0) -> list[str]:
    """
    Send commands to TCP backends with failover support.
    
    Args:
        commands: List of command strings to send to the TCP server
        timeoutSeconds: Connection timeout in seconds (default: 3.0)
    
    Returns:
        List of response strings from the TCP server
    
    Raises:
        Exception: If all TCP backends fail to connect
        RuntimeError: If no TCP backends are configured
    """
    lastException: Exception | None = None  # Track the last exception for error reporting

    # Try each TCP backend in order until one succeeds
    for tcpHost, tcpPort in tcpBackends:
        responses: list[str] = []  # Store responses from this backend
        bufferData = bytearray()    # Buffer for incoming data
        try:
            # Create TCP socket connection
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as clientSocket:
                clientSocket.settimeout(timeoutSeconds)  # Set connection timeout
                clientSocket.connect((tcpHost, tcpPort))  # Connect to TCP backend

                # Clear welcome message from server (first line is usually a greeting)
                _, bufferData = ReceiveLine(clientSocket, bufferData)

                # Send each command and collect responses
                for command in commands:
                    SendLine(clientSocket, command)  # Send command to TCP server
                    response, bufferData = ReceiveLine(clientSocket, bufferData)  # Get response
                    responses.append(response if response is not None else "")
            
            # Success! Log and return responses
            print(f"[Gateway] ✅ Éxito conectando a {tcpHost}:{tcpPort}")
            return responses
            
        except Exception as exception:
            # Connection failed, try next backend
            print(f"[Gateway] ⚠️ Falló {tcpHost}:{tcpPort}. Saltando al respaldo...")
            lastException = exception
            continue

    # All backends failed, raise the last exception
    if lastException is not None:
        raise lastException
    raise RuntimeError("No TCP backends configured")

def SendLine(socketConnection: socket.socket, message: str) -> None:
    """
    Send a line of text over a socket connection.
    
    Args:
        socketConnection: The socket to send data through
        message: The message string to send
    """
    # Add newline character and encode as UTF-8 bytes
    socketConnection.sendall((message + "\n").encode("utf-8"))


def ReceiveLine(socketConnection: socket.socket, bufferData: bytearray) -> Tuple[str | None, bytearray]:
    """
    Receive a line of text from a socket connection.
    Handles partial data reception and buffering.
    
    Args:
        socketConnection: The socket to receive data from
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
        data = socketConnection.recv(4096)  # Receive up to 4096 bytes (blocking call)
        if not data:
            # Connection closed by server
            return None, bufferData
        bufferData.extend(data)  # Add received data to buffer

# HTML template for the voting interface web page
# Provides a simple UI for users to vote and view results
HTML_PAGE = """<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Voting Gateway</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 18px; }
    button { font-size: 18px; padding: 12px 16px; margin: 8px 8px 8px 0; }
    input { font-size: 18px; padding: 10px; width: 220px; }
    .box { padding: 12px; border: 1px solid #ddd; border-radius: 10px; margin-top: 12px; }
    code { font-size: 14px; }
  </style>
</head>
<body>
  <h2>Votación (Gateway HTTP → TCP)</h2>

  <div class="box">
    <div><b>UserId</b> (único por persona):</div>
    <input id="userId" placeholder="ej. miguel" />
    <div style="margin-top:10px;">
      <button onclick="vote('A')">Votar A</button>
      <button onclick="vote('B')">Votar B</button>
      <button onclick="vote('C')">Votar C</button>
      <button onclick="results()">Ver resultados</button>
    </div>
    <pre id="out"></pre>
  </div>

<script>
async function vote(option) {
  const userId = document.getElementById('userId').value.trim();
  if (!userId) { alert("Escribe un userId"); return; }

  const body = new URLSearchParams({userId, option});
  const r = await fetch('/vote', {method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'}, body});
  const t = await r.text();
  document.getElementById('out').textContent = t;
}

async function results() {
  const r = await fetch('/results');
  const t = await r.text();
  document.getElementById('out').textContent = t;
}
</script>

  <p style="margin-top:14px; color:#666;">
    Tip: si alguien intenta votar dos veces con el mismo userId, el servidor TCP responde <code>ERR already_voted</code>.
  </p>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    """
    HTTP request handler for the voting gateway.
    
    Handles HTTP requests and forwards them to TCP backends.
    Supports:
    - GET / or /index: Returns the voting interface HTML page
    - GET /results: Returns current voting results
    - POST /vote: Processes a vote submission
    """

    def SendResponse(self, statusCode: int, contentType: str, body: str) -> None:
        """
        Send an HTTP response with the specified status, content type, and body.
        
        Args:
            statusCode: HTTP status code (e.g., 200, 404, 500)
            contentType: MIME type of the response body
            body: Response body content as string
        """
        bodyBytes = body.encode("utf-8")  # Convert body to bytes
        self.send_response(statusCode)  # Send status line
        self.send_header("Content-Type", contentType + "; charset=utf-8")  # Set content type
        self.send_header("Content-Length", str(len(bodyBytes)))  # Set content length
        self.end_headers()  # End headers section (adds \r\n)
        self.wfile.write(bodyBytes)  # Write body to response stream

    def do_GET(self):
        """
        Handle HTTP GET requests.
        
        Supported endpoints:
        - GET / or /index: Returns the voting interface HTML page
        - GET /results: Returns current voting results from TCP backend
        """
        # Serve the main voting interface page
        if self.path == "/" or self.path.startswith("/index"):
            return self.SendResponse(200, "text/html", HTML_PAGE)

        # Handle results request
        if self.path.startswith("/results"):
            try:
                # Send RESULTS command to TCP backend
                response = TcpSendCommands(["RESULTS"])
                response = response[0]  # Get first (and only) response
                return self.SendResponse(200, "text/plain", response + "\n")
            except Exception as exception:
                # Return error if TCP backend fails
                return self.SendResponse(
                    500,
                    "text/plain",
                    f"ERR gateway_failure {type(exception).__name__}:{exception}\n"
                )

        # Return 404 for unknown endpoints
        return self.SendResponse(404, "text/plain", "ERR not_found\n")

    def do_POST(self):
        """
        Handle HTTP POST requests.
        
        Supported endpoints:
        - POST /vote: Processes a vote submission with userId and option
        
        Expected form data:
        - userId: Unique identifier for the voter
        - option: Voting option (A, B, or C)
        """
        # Only handle /vote endpoint
        if self.path != "/vote":
            return self.SendResponse(404, "text/plain", "ERR not_found\n")

        # Read and parse form data from request body
        length = int(self.headers.get("Content-Length", "0"))
        rawData = self.rfile.read(length).decode("utf-8", errors="replace")
        parsedData = urllib.parse.parse_qs(rawData)

        # Extract userId and option from form data
        userId = (parsedData.get("userId", [""])[0]).strip()
        option = (parsedData.get("option", [""])[0]).strip().upper()

        # Validate required parameters
        if not userId or not option:
            return self.SendResponse(400, "text/plain", "ERR usage: userId and option required\n")

        try:
            # Send commands to TCP backend
            # NOTE: This implementation is tightly coupled to the TCP protocol
            # It expects HELLO command to register user, then VOTE command
            helloResponse, voteResponse = TcpSendCommands(
                [f"HELLO {userId}", f"VOTE {option}"]
            )

            # Return both responses to client
            body = f"{helloResponse}\n{voteResponse}\n"
            return self.SendResponse(200, "text/plain", body)

        except Exception as exception:
            # Return error if TCP backend fails
            return self.SendResponse(
                500,
                "text/plain",
                f"ERR gateway_failure {type(exception).__name__}:{exception}\n"
            )


def Main():
    """
    Main entry point for the HTTP gateway server.
    
    Starts the HTTP server that acts as a gateway between
    HTTP clients and TCP voting backends.
    """
    # Display server configuration
    backendsText = ", ".join([f"{h}:{p}" for (h, p) in tcpBackends])
    print(f"[gateway] HTTP on http://{httpHost}:{httpPort}  ->  TCP backends: {backendsText}")
    
    # Create and start the threaded HTTP server
    server = ThreadingHTTPServer((httpHost, httpPort), Handler)
    server.serve_forever()  # Run indefinitely


# Run the gateway server when this script is executed directly
if __name__ == "__main__":
    Main()
