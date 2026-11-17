# CSI201 Coursework I — Networked Quiz Tournament

**Status:** implementation draft for team review and Docker verification. The team must verify all behaviour in the examiner-provided image before submission.

## Requirements
- Python 3.12
- Standard Library only
- Raw TCP sockets; no GUI, database, web framework or package installation

## Start the server
From the `Codes` directory:

```bash
python3 server.py --host 0.0.0.0 --port 5000 --questions questions.json
```

The server prints `SERVER_READY` only after validating the complete question bank and successfully binding/listening.

## Start clients
In separate terminals:

```bash
python3 client.py --server 127.0.0.1 --port 5000 --id player1 --name Alice
python3 client.py --server 127.0.0.1 --port 5000 --id player2 --name Bob
```

## CLI commands
| Command | Purpose |
|---|---|
| `/help` | Show command summary |
| `/quizzes` | List public quiz metadata |
| `/rooms` | List joinable rooms |
| `/create <quiz_id>` | Create a room and become host |
| `/join <room_code>` | Join a lobby |
| `/players` | Show room participants and readiness |
| `/ready` | Mark the current player ready |
| `/start` | Host requests quiz start |
| `/answer <A\|B\|C\|D>` | Submit one answer for the current question |
| `/score` | Show leaderboard |
| `/leave` | Leave current room |
| `/quit` | Log out and close client |

A room requires at least two players and all players must be ready. The host must also use `/ready`.

## Docker environment
The supplied environment ZIP contains a Python 3.12 Dockerfile and Compose file. From the extracted environment directory, copy/mount the `Codes` contents into `/code` or build the supplied Compose service with the code directory mounted there. The module's examiner image/tag on Learning Mall takes precedence over this development environment.

Example using the supplied Compose setup (run from the directory containing `compose.yaml`):

```bash
docker compose run --rm python --version
docker compose run --rm -it -v "$(pwd)/../Codes:/code" -w /code python server.py --host 0.0.0.0 --port 5000 --questions questions.json
```

Use a second terminal/container for each client. Confirm the exact networking invocation with your team and the examiner image configuration.

## Tests
From `Codes`:

```bash
python3 -m unittest discover -s tests -v
```

These unit tests cover question-bank acceptance, selected invalid inputs, fragmented TCP frames, coalesced frames and zero-length frame rejection. They do **not** establish full paired-workflow, ten-client, two-room, timing, malformed-frame or examiner-Docker compliance. Those tests must be run and recorded by the team in the official environment.

## Protocol summary
Each TCP application message is a four-byte unsigned big-endian payload length followed by a UTF-8 JSON object. Maximum payload: 65,536 bytes. Messages use `version`, `type`, `request_id`, `session_id`, and `payload`. Server events use `event_id`. The implementation uses message names documented in the Development Documentation.

## Assumptions and limitations to verify
- The host is transferred to the first remaining player if the host disconnects or leaves during the lobby.
- The lobby has a maximum of 20 players; a room requires at least two players.
- The server uses one handler thread per connection and one quiz worker thread per active room.
- Scores award the configured points for a correct answer and zero otherwise; no speed bonus is used.
- The client is a basic terminal interface. The team must exercise malformed frames, client disconnects, host departure during play, ten concurrent clients, two simultaneous rooms and Ctrl+C before making claims of full compliance.
