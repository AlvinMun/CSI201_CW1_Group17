#!/usr/bin/env python3
"""CSI201 command-line quiz client."""
import argparse, json, queue, socket, struct, threading, secrets, sys
MAX_FRAME=65536

def recv_exact(sock,n):
    b=bytearray()
    while len(b)<n:
        x=sock.recv(n-len(b))
        if not x: return None
        b.extend(x)
    return bytes(b)
def receive(sock):
    h=recv_exact(sock,4)
    if h is None: return None
    n=struct.unpack('!I',h)[0]
    if not 1<=n<=MAX_FRAME: raise ValueError('invalid frame length')
    raw=recv_exact(sock,n)
    if raw is None: return None
    obj=json.loads(raw.decode('utf-8'))
    if not isinstance(obj,dict): raise ValueError('invalid message object')
    return obj
def send(sock,lock,typ,payload=None):
    msg={'version':1,'type':typ,'request_id':secrets.token_hex(6),'session_id':None,'payload':payload or {}}
    raw=json.dumps(msg,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    with lock: sock.sendall(struct.pack('!I',len(raw))+raw)

def display(msg):
    typ=msg.get('type'); p=msg.get('payload',{})
    if typ == 'QUESTION_EVENT': main.current_question = p.get('question_id')
    if typ=='ERROR_RESPONSE': print(f"[ERROR {p.get('code')}] {p.get('message')}")
    elif typ=='LIST_QUIZZES_RESPONSE':
        print('\nAvailable quizzes:')
        for q in p.get('quizzes',[]): print(f"  {q['quiz_id']}: {q['title']} ({q['question_count']} questions) - {q.get('description','')}")
    elif typ=='LIST_ROOMS_RESPONSE':
        print('\nJoinable rooms:')
        for r in p.get('rooms',[]): print(f"  {r['room_code']} | {r['quiz_id']} | host={r['host']} | players={len(r['players'])}")
    elif typ in ('CREATE_ROOM_RESPONSE','JOIN_ROOM_RESPONSE'): print(json.dumps(p,ensure_ascii=False,indent=2))
    elif typ in ('PLAYER_LIST_RESPONSE','PLAYER_STATUS_EVENT'): 
        print('\nRoom participants:')
        for x in p.get('players',[]): print(f"  {x['name']} ({x['user_id']}) - {'READY' if x['ready'] else 'NOT READY'}")
    elif typ=='READY_RESPONSE': print('Readiness updated.')
    elif typ=='START_QUIZ_RESPONSE': print('Quiz start accepted.')
    elif typ=='QUIZ_STARTED_EVENT': print(f"\n=== QUIZ STARTED: {p.get('title')} ({p.get('total_questions')} questions) ===")
    elif typ=='QUESTION_EVENT':
        print(f"\nQUESTION {p['number']} [{p['time_limit']}s, {p['points']} pts]\n{p['text']}")
        for k,v in p['options'].items(): print(f"  {k}. {v}")
        print('Submit with: /answer A')
    elif typ=='ANSWER_RESPONSE': print('Answer accepted by server.')
    elif typ=='QUESTION_RESULT_EVENT':
        print(f"\nCorrect answer: {p['correct_answer']}")
        for uid,pts in p.get('points_awarded',{}).items(): print(f"  {uid}: {pts} points")
        print_leaderboard(p.get('leaderboard',[]))
    elif typ in ('LEADERBOARD_RESPONSE',): print_leaderboard(p.get('leaderboard',[]))
    elif typ=='QUIZ_FINISHED_EVENT': print('\n=== QUIZ FINISHED ==='); print_leaderboard(p.get('final_leaderboard',[])); print('Winner:',p.get('winner'))
    elif typ=='LEAVE_ROOM_RESPONSE': print('You left the room.')
    elif typ=='LOGOUT_RESPONSE': print('Logged out.')
    elif typ not in ('LOGIN_RESPONSE',): print(f'[{typ}] {json.dumps(p,ensure_ascii=False)}')
def print_leaderboard(rows):
    print('\nLeaderboard:')
    for i,x in enumerate(rows,1): print(f"  {i}. {x.get('name',x.get('user_id'))} - {x.get('score',0)}")

def main():
    ap=argparse.ArgumentParser(description='CSI201 networked quiz tournament client')
    ap.add_argument('--server',required=True); ap.add_argument('--port',required=True,type=int); ap.add_argument('--id',required=True); ap.add_argument('--name',required=True)
    a = ap.parse_args()
    main.current_question = None
    sock = socket.create_connection((a.server, a.port), timeout=10)
    sock.settimeout(None)
    lock = threading.Lock()
    stop = threading.Event()
    commands = queue.Queue(maxsize=1)

    def read_commands():
        # An idle input thread must not hold Python's buffered stdin lock at exit.
        with open(sys.stdin.fileno(), 'rb', buffering=0, closefd=False) as terminal:
            while not stop.is_set():
                raw = terminal.readline()
                if not raw:
                    commands.put('/quit')
                    return
                commands.put(raw.decode(sys.stdin.encoding or 'utf-8', errors='replace').strip())

    def reader():
        try:
            while not stop.is_set():
                msg=receive(sock)
                if msg is None: break
                display(msg)
        except (OSError,ValueError,json.JSONDecodeError) as e: print(f'Connection reader stopped: {e}',file=sys.stderr)
        finally:
            stop.set()
            print('Disconnected from server.', flush=True)

    reader_thread = threading.Thread(target=reader, daemon=True)
    reader_thread.start()
    send(sock,lock,'LOGIN_REQUEST',{'user_id':a.id,'name':a.name})
    print('\nCommands: /help /quizzes /rooms /create <quiz_id> /join <room_code> /players /ready /start /answer <A|B|C|D> /score /leave /quit')
    threading.Thread(target=read_commands, daemon=True).start()
    try:
        while not stop.is_set():
            print('quiz> ', end='', flush=True)
            while not stop.is_set():
                try:
                    line = commands.get(timeout=0.1)
                    break
                except queue.Empty:
                    continue
            if stop.is_set():
                break
            if not line:
                continue
            parts=line.split(); cmd=parts[0].lower()
            try:
                if cmd=='/help': print('Use /quizzes, /rooms, /create ID, /join CODE, /players, /ready, /start, /answer A, /score, /leave, /quit.')
                elif cmd=='/quizzes': send(sock,lock,'LIST_QUIZZES_REQUEST')
                elif cmd=='/rooms': send(sock,lock,'LIST_ROOMS_REQUEST')
                elif cmd=='/create' and len(parts)==2: send(sock,lock,'CREATE_ROOM_REQUEST',{'quiz_id':parts[1]})
                elif cmd=='/join' and len(parts)==2: send(sock,lock,'JOIN_ROOM_REQUEST',{'room_code':parts[1]})
                elif cmd=='/players': send(sock,lock,'PLAYER_LIST_REQUEST')
                elif cmd=='/ready': send(sock,lock,'READY_REQUEST',{'ready':True})
                elif cmd=='/start': send(sock,lock,'START_QUIZ_REQUEST')
                elif cmd=='/answer' and len(parts)==2: send(sock,lock,'ANSWER_REQUEST',{'question_id':getattr(main,'current_question',None),'answer':parts[1].upper()})
                elif cmd=='/score': send(sock,lock,'LEADERBOARD_REQUEST')
                elif cmd=='/leave': send(sock,lock,'LEAVE_ROOM_REQUEST')
                elif cmd=='/quit': send(sock,lock,'LOGOUT_REQUEST'); break
                else: print('Invalid command. Type /help.')
            except OSError as e: print(f'Unable to send: {e}'); break
    except KeyboardInterrupt: pass
    finally:
        stop.set()
        try: sock.shutdown(socket.SHUT_RDWR)
        except OSError: pass
        sock.close()
        reader_thread.join()
if __name__=='__main__': main()
