
import socket
import json
import struct
import secrets

HOST = "127.0.0.1"
PORT = 5000

def send(sock, message):
    raw = json.dumps(message).encode("utf-8")
    sock.sendall(struct.pack("!I", len(raw)) + raw)

def receive(sock):
    header = sock.recv(4)
    if len(header) != 4:
        return None

    length = struct.unpack("!I", header)[0]
    data = b""

    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            return None
        data += chunk

    return json.loads(data.decode("utf-8"))

with socket.create_connection((HOST, PORT), timeout=5) as sock:
    sock.settimeout(5)

    send(sock, {
        "version": "one",
        "type": "LOGIN_REQUEST",
        "request_id": secrets.token_hex(6),
        "session_id": None,
        "payload": {
            "user_id": "envelope_test",
            "name": "Envelope Tester"
        }
    })

    response = receive(sock)
    print("Malformed envelope response:", response)
