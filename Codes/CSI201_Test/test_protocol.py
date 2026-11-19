
import socket
import struct
import json

HOST = "127.0.0.1"
PORT = 5000


def send_raw(sock, data):
    sock.sendall(struct.pack("!I", len(data)) + data)


def receive_message(sock):
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


def test_invalid_envelope():
    print("\nTest: Invalid message envelope")

    with socket.create_connection((HOST, PORT), timeout=5) as sock:
        sock.settimeout(5)

        # Valid JSON, but missing required envelope fields.
        message = {
            "version": 1,
            "type": "LIST_QUIZZES_REQUEST"
        }

        raw = json.dumps(message).encode("utf-8")
        send_raw(sock, raw)

        response = receive_message(sock)
        print("Server response:", response)

def test_invalid_json():
    print("\nTest: Invalid JSON")

    with socket.create_connection((HOST, PORT), timeout=5) as sock:
        sock.settimeout(5)

        # Deliberately malformed JSON.
        raw = b'{"version": 1, "type": INVALID_JSON}'
        send_raw(sock, raw)

        try:
            response = receive_message(sock)
            print("Server response:", response)
        except (ConnectionError, OSError, ValueError) as e:
            print("Connection closed or invalid response:", e)

def test_invalid_session():
    print("\nTest: Invalid session ID")

    with socket.create_connection((HOST, PORT), timeout=5) as sock:
        sock.settimeout(5)

        message = {
            "version": 1,
            "type": "LIST_QUIZZES_REQUEST",
            "request_id": "test123",
            "session_id": "invalid_session",
            "payload": {}
        }

        raw = json.dumps(message).encode("utf-8")
        send_raw(sock, raw)

        response = receive_message(sock)
        print("Server response:", response)

if __name__ == "__main__":
    test_invalid_envelope()
    test_invalid_json()
    test_invalid_session()