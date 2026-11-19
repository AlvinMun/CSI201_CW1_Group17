
import socket
import json
import struct
import secrets

HOST = "127.0.0.1"
PORT = 5000

def recv_exact(sock, n):
    data = bytearray()
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Connection closed")
        data.extend(chunk)
    return bytes(data)

def send(sock, message):
    raw = json.dumps(message).encode("utf-8")
    sock.sendall(struct.pack("!I", len(raw)) + raw)

def receive(sock):
    header = recv_exact(sock, 4)
    length = struct.unpack("!I", header)[0]
    raw = recv_exact(sock, length)
    return json.loads(raw.decode("utf-8"))

def request(sock, typ, session_id, payload):
    send(sock, {
        "version": 1,
        "type": typ,
        "request_id": secrets.token_hex(6),
        "session_id": session_id,
        "payload": payload
    })
    return receive(sock)

with socket.create_connection((HOST, PORT), timeout=5) as sock:
    sock.settimeout(5)

    # 1. Login
    login = request(sock, "LOGIN_REQUEST", None, {
        "user_id": "malformed_test",
        "name": "Malformed Tester"
    })
    print("Login:", login)

    session_id = login["session_id"]
    # Test an incorrect session token after login
    response = request(
        sock,
        "LIST_QUIZZES_REQUEST",
        "WRONG_SESSION_TOKEN",
        {}
    )

    print("Invalid session response:", response)

    # 2. Retrieve available quizzes
    quizzes_response = request(
        sock, "LIST_QUIZZES_REQUEST", session_id, {}
    )

    quizzes = quizzes_response["payload"]["quizzes"]
    quiz_id = quizzes[0]["quiz_id"]

    print("Selected quiz:", quiz_id)

    # 3. Create a room
    # 3. Send CREATE_ROOM_REQUEST without quiz_id
    room_response = request(
        sock, "CREATE_ROOM_REQUEST", session_id,
        {}
    )

    print("Missing field response:", room_response)

    # 4. Send an invalid READY_REQUEST
    malformed_response = request(
        sock, "READY_REQUEST", session_id,
        {"ready": "yes"}
    )

    print("Malformed request response:", malformed_response)
