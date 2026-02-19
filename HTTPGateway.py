from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
import urllib.parse
from typing import Tuple

# TCP backends (primary first, then fallback)
tcpBackends = [
    ("127.0.0.1", 5050),
    ("127.0.0.1", 5051),
]

httpHost = "0.0.0.0"
httpPort = 8080


def TcpSendCommands(commands: list[str], timeoutSeconds: float = 3.0) -> list[str]:
    lastException: Exception | None = None

    for tcpHost, tcpPort in tcpBackends:
        responses: list[str] = []
        bufferData = bytearray()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as clientSocket:
                clientSocket.settimeout(timeoutSeconds)
                clientSocket.connect((tcpHost, tcpPort))

                _, bufferData = ReceiveLine(clientSocket, bufferData)#clear welcome message from server

                for command in commands:
                    SendLine(clientSocket, command)
                    response, bufferData = ReceiveLine(clientSocket, bufferData)
                    responses.append(response if response is not None else "")

            return responses
        except Exception as exception:
            lastException = exception
            continue

    if lastException is not None:
        raise lastException
    raise RuntimeError("No TCP backends configured")

def SendLine(socketConnection: socket.socket, message: str) -> None:
    socketConnection.sendall((message + "\n").encode("utf-8"))


def ReceiveLine(socketConnection: socket.socket, bufferData: bytearray) -> Tuple[str | None, bytearray]:
    while True:#data arrives in pieces
        newlineIndex = bufferData.find(b"\n")
        if newlineIndex != -1:
            line = bufferData[:newlineIndex].decode("utf-8", errors="replace").rstrip("\r")
            bufferData = bufferData[newlineIndex + 1:]
            #line: command at a time delimited by \n
            #bufferData: unprocessed stream \n
            return line, bufferData 

        data = socketConnection.recv(4096) #4096 as byte limit, Blocking state
        if not data:
            return None, bufferData
        bufferData.extend(data)

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

    def SendResponse(self, statusCode: int, contentType: str, body: str) -> None:
        bodyBytes = body.encode("utf-8")
        self.send_response(statusCode)
        self.send_header("Content-Type", contentType + "; charset=utf-8")
        self.send_header("Content-Length", str(len(bodyBytes)))
        self.end_headers() #append /r/n
        self.wfile.write(bodyBytes)#socket output stream

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            return self.SendResponse(200, "text/html", HTML_PAGE)

        if self.path.startswith("/results"):
            try:
                response = TcpSendCommands(["RESULTS"])
                response = response[0]
                return self.SendResponse(200, "text/plain", response + "\n")
            except Exception as exception:
                return self.SendResponse(
                    500,
                    "text/plain",
                    f"ERR gateway_failure {type(exception).__name__}:{exception}\n"
                )

        return self.SendResponse(404, "text/plain", "ERR not_found\n")

    def do_POST(self):
        if self.path != "/vote":
            return self.SendResponse(404, "text/plain", "ERR not_found\n")

        length = int(self.headers.get("Content-Length", "0"))
        rawData = self.rfile.read(length).decode("utf-8", errors="replace")
        parsedData = urllib.parse.parse_qs(rawData)

        userId = (parsedData.get("userId", [""])[0]).strip()
        option = (parsedData.get("option", [""])[0]).strip().upper()

        if not userId or not option:
            return self.SendResponse(400, "text/plain", "ERR usage: userId and option required\n")

        try:
            #tigthly coupled, not ok
            helloResponse, voteResponse = TcpSendCommands(
                [f"HELLO {userId}", f"VOTE {option}"]
            )

            body = f"{helloResponse}\n{voteResponse}\n"
            return self.SendResponse(200, "text/plain", body)

        except Exception as exception:
            return self.SendResponse(
                500,
                "text/plain",
                f"ERR gateway_failure {type(exception).__name__}:{exception}\n"
            )


def Main():
    backendsText = ", ".join([f"{h}:{p}" for (h, p) in tcpBackends])
    print(f"[gateway] HTTP on http://{httpHost}:{httpPort}  ->  TCP backends: {backendsText}")
    server = ThreadingHTTPServer((httpHost, httpPort), Handler)
    server.serve_forever()


if __name__ == "__main__":
    Main()
