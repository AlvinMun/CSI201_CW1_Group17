# CSI201 Coursework I — Networked Quiz Tournament

**Status:** implementation draft for team review and Docker verification. The team must verify all behaviour in the examiner-provided image before submission.

## Requirements
- Python 3.12
- Standard Library only
- Raw TCP sockets; no GUI, database, web framework or package installation

## Run in the examiner Docker environment

Use the `CSI201_CW1_Docker_Env` package from Learning Mall for verification and demonstrations. Its Compose file builds the Python 3.12 image tagged `csi201-cw1:latest`.

### Build the course image

Start Docker Desktop. In File Explorer, open the extracted `CSI201_CW1_Docker_Env` folder that contains `compose.yaml`. Type `powershell` in the address bar and press Enter to open PowerShell in that folder. Run:

```powershell
docker compose build python
```

### Start the server

After the build completes, open the project's `Codes` folder in File Explorer. Make sure `compose.yaml`, `server.py` and `questions.json` are in this folder. Type `powershell` in the address bar and press Enter, then run:

```powershell
docker compose run --rm --name csi201-quiz python server.py --host 0.0.0.0 --port 5000 --questions questions.json
```

Wait for `SERVER_READY` and keep the server terminal open. The server prints this line after validating the question bank and opening its listening socket.

Include `Codes/compose.yaml` in the submission ZIP so the command can be reproduced. It mounts `Codes` at `/code` and uses the official image built in the previous step. Omit the Dockerfile and Docker image from the ZIP as required by the coursework.

### Start the clients

Open two more terminals and run one command in each. Both client processes run in the server container and connect to its port 5000 over TCP. Only the server reads `questions.json`.

```powershell
docker exec -it csi201-quiz python client.py --server 127.0.0.1 --port 5000 --id player1 --name Alice
docker exec -it csi201-quiz python client.py --server 127.0.0.1 --port 5000 --id player2 --name Bob
```

If you choose a different port, use it in the server and both client commands. Use `/quit` to exit each client and Ctrl+C in the server terminal to stop the server.

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

## Tests

With the examiner container running, run the unit tests from another terminal.

```powershell
docker exec csi201-quiz python3 -m unittest discover -s tests -v
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
