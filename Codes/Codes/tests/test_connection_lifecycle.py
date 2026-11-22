import socket
import subprocess
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock


CODES = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODES))
from server import Player, Server, recv_message


class ConnectionLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.server = Server('127.0.0.1', 5000, [{'quiz_id': 'demo'}])
        self.host = self.login('host')
        self.server.dispatch(self.host, 'CREATE_ROOM_REQUEST', {'quiz_id': 'demo'}, None)
        self.room = self.server.rooms[self.host.room]

    def login(self, user_id, name=None):
        player = Player(Mock(spec=socket.socket), None)
        player.send = Mock()
        self.server.dispatch(player, 'LOGIN_REQUEST', {'user_id': user_id, 'name': name or user_id}, None)
        return player

    def test_last_player_logout_removes_lobby(self):
        self.server.dispatch(self.host, 'LOGOUT_REQUEST', {}, None)
        self.assertEqual(self.room.state, 'CLOSED')
        self.assertNotIn(self.room.code, self.server.rooms)
        self.assertNotIn('host', self.server.players)

    def test_disconnected_host_transfers_room_to_remaining_player(self):
        guest = self.login('guest')
        self.server.dispatch(guest, 'JOIN_ROOM_REQUEST', {'room_code': self.room.code}, None)
        self.server.drop(self.host)
        self.assertIs(self.room.host, guest)
        self.assertEqual(set(self.room.players), {'guest'})
        self.assertEqual(self.room.state, 'LOBBY')

    def test_rejected_second_login_keeps_original_identity(self):
        session = self.host.session
        self.server.dispatch(self.host, 'LOGIN_REQUEST', {'user_id': 'new', 'name': 'New'}, 'second')
        response_type, payload, request_id = self.host.send.call_args.args
        self.assertEqual((response_type, payload['code'], request_id),
                         ('ERROR_RESPONSE', 'ALREADY_LOGGED_IN', 'second'))
        self.assertEqual((self.host.user_id, self.host.session), ('host', session))
        self.assertEqual(set(self.room.players), {'host'})
        self.assertNotIn('new', self.server.players)
        self.server.drop(self.host)
        self.assertIs(self.login('host'), self.server.players['host'])

    def test_different_user_id_cannot_use_an_active_display_name(self):
        for name in ('host', ' Host '):
            with self.subTest(name=name):
                guest = self.login('guest', name)
                response_type, payload, _ = guest.send.call_args.args
                self.assertEqual((response_type, payload['code']), ('ERROR_RESPONSE', 'DUPLICATE_NAME'))
                self.assertNotIn('guest', self.server.players)

    def test_display_name_can_be_reused_after_logout(self):
        self.server.dispatch(self.host, 'LOGOUT_REQUEST', {}, None)
        guest = self.login('guest', 'Host')
        self.assertEqual(guest.send.call_args.args[0], 'LOGIN_RESPONSE')
        self.assertIs(self.server.players['guest'], guest)


class ClientDisconnectTests(unittest.TestCase):
    def test_disconnected_client_exits_while_waiting_for_input(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            listener.settimeout(5)
            port = str(listener.getsockname()[1])
            with subprocess.Popen(
                [sys.executable, '-u', str(CODES / 'client.py'), '--server', '127.0.0.1',
                 '--port', port, '--id', 'client', '--name', 'Client'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            ) as client:
                prompt_seen = threading.Event()

                def wait_for_prompt():
                    recent = ''
                    for char in iter(lambda: client.stdout.read(1), ''):
                        recent = (recent + char)[-6:]
                        if recent == 'quiz> ':
                            prompt_seen.set()
                            return

                output_reader = threading.Thread(target=wait_for_prompt)
                output_reader.start()
                try:
                    conn, _ = listener.accept()
                    with conn:
                        conn.settimeout(5)
                        self.assertEqual(recv_message(conn)['type'], 'LOGIN_REQUEST')
                        self.assertTrue(prompt_seen.wait(5), 'client did not reach the input prompt')
                    self.assertEqual(client.wait(timeout=5), 0)
                    self.assertIn('Disconnected from server.', client.stdout.read())
                finally:
                    if client.poll() is None:
                        client.kill()
                    output_reader.join()
