#!/usr/bin/env python3
"""CSI201 Networked Quiz Tournament server (Python 3.12 standard library only)."""
import argparse, json, socket, struct, threading, time, secrets, re, sys
from pathlib import Path

MAX_FRAME = 65536
ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,32}$')

def recv_exact(sock, n):
    data = bytearray()
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            return None
        data.extend(chunk)
    return bytes(data)

def recv_message(sock):
    head = recv_exact(sock, 4)
    if head is None: return None
    size = struct.unpack('!I', head)[0]
    if not 1 <= size <= MAX_FRAME: raise ValueError('invalid frame length')
    raw = recv_exact(sock, size)
    if raw is None: raise ConnectionError('truncated frame')
    obj = json.loads(raw.decode('utf-8'))
    if not isinstance(obj, dict): raise ValueError('message must be a JSON object')
    return obj

def send_message(sock, lock, msg):
    raw = json.dumps(msg, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    if not 1 <= len(raw) <= MAX_FRAME: raise ValueError('outgoing frame too large')
    packet = struct.pack('!I', len(raw)) + raw
    with lock: sock.sendall(packet)

def load_questions(path):
    p = Path(path)
    raw = p.read_bytes()
    if not raw or len(raw) > 1_000_000: raise ValueError('question bank must be 1 byte to 1 MB')
    try: data = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as e: raise ValueError(f'invalid UTF-8 JSON: {e}')
    if not isinstance(data, dict): raise ValueError('top level must be an object')
    if type(data.get('schema_version')) is not int or data['schema_version'] != 1: raise ValueError('schema_version must be integer 1')
    quizzes = data.get('quizzes')
    if not isinstance(quizzes, list) or not 1 <= len(quizzes) <= 20: raise ValueError('quizzes must contain 1 to 20 entries')
    qids, quizids = set(), set()
    for qi, quiz in enumerate(quizzes):
        if not isinstance(quiz, dict): raise ValueError(f'quiz {qi}: must be an object')
        qid, title, desc, questions = quiz.get('quiz_id'), quiz.get('title'), quiz.get('description'), quiz.get('questions')
        if not isinstance(qid, str) or not ID_RE.fullmatch(qid) or qid in quizids: raise ValueError(f'quiz {qi}: invalid or duplicate quiz_id')
        quizids.add(qid)
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 100: raise ValueError(f'{qid}: title must be 1-100 visible characters')
        if not isinstance(desc, str) or len(desc) > 300: raise ValueError(f'{qid}: description must be 0-300 characters')
        if not isinstance(questions, list) or not 5 <= len(questions) <= 50: raise ValueError(f'{qid}: questions must contain 5-50 entries')
        for j, q in enumerate(questions):
            where=f'{qid} question {j}'
            if not isinstance(q, dict): raise ValueError(f'{where}: must be an object')
            ident=q.get('question_id'); text=q.get('text'); opts=q.get('options'); ans=q.get('answer'); tl=q.get('time_limit'); pts=q.get('points')
            if not isinstance(ident,str) or not ID_RE.fullmatch(ident) or ident in qids: raise ValueError(f'{where}: invalid or duplicate question_id')
            qids.add(ident)
            if not isinstance(text,str) or not 1 <= len(text.strip()) <= 500: raise ValueError(f'{where}: text must be 1-500 characters')
            if not isinstance(opts,dict) or set(opts) != {'A','B','C','D'}: raise ValueError(f'{where}: options must have exactly A, B, C, D')
            if any(not isinstance(v,str) or not 1 <= len(v) <= 200 for v in opts.values()): raise ValueError(f'{where}: each option must be 1-200 characters')
            if ans not in ('A','B','C','D'): raise ValueError(f'{where}: answer must be A, B, C or D')
            if type(tl) is not int or not 5 <= tl <= 60: raise ValueError(f'{where}: time_limit must be 5-60')
            if type(pts) is not int or not 1 <= pts <= 1000: raise ValueError(f'{where}: points must be 1-1000')
    return quizzes

class Player:
    def __init__(self, sock, addr):
        self.sock=sock; self.addr=addr; self.send_lock=threading.Lock(); self.user_id=None; self.name=None; self.session=None; self.room=None; self.alive=True
    def send(self, typ, payload=None, request_id=None, event=False):
        msg={'version':1,'type':typ,'request_id':request_id,'event_id':secrets.token_hex(6) if event else None,'session_id':self.session,'payload':payload or {}}
        send_message(self.sock,self.send_lock,msg)

class Room:
    def __init__(self, code, quiz, host):
        self.code=code; self.quiz=quiz; self.host=host; self.players={host.user_id:host}; self.ready={host.user_id:False}; self.state='LOBBY'; self.lock=threading.RLock(); self.current_q=None; self.answers={}; self.scores={host.user_id:0}; self.thread=None
    def snapshot(self):
        return {'room_code':self.code,'quiz_id':self.quiz['quiz_id'],'state':self.state,'host':self.host.user_id,'players':[{'user_id':p.user_id,'name':p.name,'ready':self.ready.get(p.user_id,False)} for p in self.players.values()]}

class Server:
    def __init__(self, host, port, questions):
        self.host=host; self.port=port; self.quizzes={q['quiz_id']:q for q in questions}; self.players={}; self.rooms={}; self.lock=threading.RLock(); self.listener=None; self.stopping=threading.Event()
    def broadcast(self, room, typ, payload):
        with room.lock: recipients=list(room.players.values())
        for p in recipients:
            try: p.send(typ,payload,event=True)
            except OSError: self.drop(p)
    def error(self,p,req,code,message):
        p.send('ERROR_RESPONSE',{'code':code,'message':message},req)

    def remove_from_room(self, player, room):
        with room.lock:
            if room.players.get(player.user_id) is not player:
                return None
            del room.players[player.user_id]
            room.ready.pop(player.user_id, None)
            room.scores.pop(player.user_id, None)
            player.room = None
            if room.players:
                if room.host is player:
                    room.host = next(iter(room.players.values()))
                return room.snapshot()
            room.state = 'CLOSED'
        with self.lock:
            self.rooms.pop(room.code, None)
        return None

    def drop(self,p):
        with self.lock:
            if not p.alive: return
            p.alive = False
            room = self.rooms.get(p.room)
        snapshot = self.remove_from_room(p, room) if room else None
        with self.lock:
            if self.players.get(p.user_id) is p:
                del self.players[p.user_id]
        try:
            p.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        p.sock.close()
        if snapshot is not None:
            self.broadcast(room, 'PLAYER_STATUS_EVENT', snapshot)
    def handle(self,p):
        try:
            while p.alive and not self.stopping.is_set():
                msg=recv_message(p.sock)
                if msg is None: break
                if msg.get('version') != 1 or not isinstance(msg.get('type'),str) or not isinstance(msg.get('payload'),dict):
                    self.error(p,msg.get('request_id'),'INVALID_MESSAGE','Invalid message envelope'); continue
                typ = msg['type']
                data = msg['payload']
                req = msg.get('request_id')

                # Validate session ID for authenticated requests.
                if typ != 'LOGIN_REQUEST':
                    if not p.session or msg.get('session_id') != p.session:
                        self.error(
                            p,
                            req,
                            'INVALID_SESSION',
                            'Invalid or missing session ID'
                        )
                        continue

                try:
                    self.dispatch(p, typ, data, req)
                except (ValueError, KeyError, TypeError) as e:
                    self.error(p, req, 'INVALID_MESSAGE', str(e))
        except (OSError,ConnectionError,ValueError,json.JSONDecodeError): pass
        finally: self.drop(p)
    def dispatch(self,p,typ,d,req):
        if typ=='LOGIN_REQUEST':
            if p.session is not None:
                return self.error(p, req, 'ALREADY_LOGGED_IN', 'This connection is already logged in')
            uid=d.get('user_id'); name=d.get('name')
            if not isinstance(uid,str) or not ID_RE.fullmatch(uid): return self.error(p,req,'INVALID_USER_ID','User ID must be 1-32 letters, digits, _ or -')
            if not isinstance(name,str) or not 1 <= len(name.strip()) <= 40: return self.error(p,req,'INVALID_NAME','Display name must be 1-40 characters')
            with self.lock:
                if uid in self.players: return self.error(p,req,'DUPLICATE_USER','This user ID is already active')
                p.user_id=uid; p.name=name.strip(); p.session=secrets.token_hex(12); self.players[uid]=p
            p.send('LOGIN_RESPONSE',{'success':True,'session_id':p.session},req); return
        if not p.session: return self.error(p,req,'INVALID_SESSION','Login first')
        if typ=='LIST_QUIZZES_REQUEST':
            p.send('LIST_QUIZZES_RESPONSE',{'quizzes':[{'quiz_id':q['quiz_id'],'title':q['title'],'description':q['description'],'question_count':len(q['questions'])} for q in self.quizzes.values()]},req)
        elif typ=='LIST_ROOMS_REQUEST':
            with self.lock: rooms=[r.snapshot() for r in self.rooms.values() if r.state=='LOBBY']
            p.send('LIST_ROOMS_RESPONSE',{'rooms':rooms},req)
        elif typ=='CREATE_ROOM_REQUEST':
            qid=d.get('quiz_id')
            if qid not in self.quizzes: return self.error(p,req,'QUIZ_NOT_FOUND','Quiz does not exist')
            if p.room: return self.error(p,req,'ALREADY_IN_ROOM','Leave your current room first')
            with self.lock:
                code=secrets.token_hex(3).upper()
                while code in self.rooms: code=secrets.token_hex(3).upper()
                r=Room(code,self.quizzes[qid],p); self.rooms[code]=r; p.room=code
            p.send('CREATE_ROOM_RESPONSE',{'success':True,'room_code':code},req)
        elif typ=='JOIN_ROOM_REQUEST':
            code=d.get('room_code');
            with self.lock: r=self.rooms.get(code)
            if not r: return self.error(p,req,'ROOM_NOT_FOUND','Room does not exist')
            with r.lock:
                if r.state!='LOBBY': return self.error(p,req,'ROOM_CLOSED','Room is no longer joinable')
                if p.room: return self.error(p,req,'ALREADY_IN_ROOM','Leave your current room first')
                if len(r.players)>=20: return self.error(p,req,'ROOM_FULL','Room is full')
                r.players[p.user_id]=p; r.ready[p.user_id]=False; r.scores[p.user_id]=0; p.room=code
            p.send('JOIN_ROOM_RESPONSE',{'success':True,'room':r.snapshot()},req); self.broadcast(r,'PLAYER_STATUS_EVENT',r.snapshot())
        elif typ=='PLAYER_LIST_REQUEST':
            r=self.get_room(p,req); 
            if r: p.send('PLAYER_LIST_RESPONSE',r.snapshot(),req)
        elif typ=='READY_REQUEST':
            r=self.get_room(p,req)
            if r:
                ready=d.get('ready',True)
                if type(ready) is not bool: return self.error(p,req,'INVALID_MESSAGE','ready must be boolean')
                with r.lock: r.ready[p.user_id]=ready; snap=r.snapshot()
                p.send('READY_RESPONSE',{'success':True,'ready':ready},req); self.broadcast(r,'PLAYER_STATUS_EVENT',snap)
        elif typ=='START_QUIZ_REQUEST':
            r=self.get_room(p,req)
            if r:
                with r.lock:
                    if r.host is not p: return self.error(p,req,'NOT_ROOM_HOST','Only the host can start')
                    if r.state!='LOBBY': return self.error(p,req,'INVALID_ROOM_STATE','Room is not in lobby')
                    if len(r.players)<2: return self.error(p,req,'NOT_ENOUGH_PLAYERS','At least two players are required')
                    if not all(r.ready.values()): return self.error(p,req,'PLAYERS_NOT_READY','All players must be ready')
                    r.state='PLAYING'; r.thread=threading.Thread(target=self.play,args=(r,),daemon=True)
                p.send('START_QUIZ_RESPONSE',{'success':True},req)
                r.thread.start()
        elif typ=='ANSWER_REQUEST':
            r=self.get_room(p,req)
            if r:
                qid=d.get('question_id'); answer=d.get('answer')
                with r.lock:
                    if r.state!='PLAYING' or not r.current_q: return self.error(p,req,'QUESTION_CLOSED','No question is open')
                    if qid != r.current_q['question_id']: return self.error(p,req,'INVALID_QUESTION','Question ID does not match')
                    if answer not in ('A','B','C','D'): return self.error(p,req,'INVALID_ANSWER','Answer must be A, B, C or D')
                    if time.monotonic() > r.deadline: return self.error(p,req,'QUESTION_CLOSED','Deadline has passed')
                    if p.user_id in r.answers: return self.error(p,req,'DUPLICATE_ANSWER','Only one answer is accepted per question')
                    r.answers[p.user_id]=answer
                p.send('ANSWER_RESPONSE',{'accepted':True,'question_id':qid},req)
        elif typ=='LEADERBOARD_REQUEST':
            r=self.get_room(p,req)
            if r: p.send('LEADERBOARD_RESPONSE',{'leaderboard':self.leaderboard(r)},req)
        elif typ=='LEAVE_ROOM_REQUEST':
            r=self.get_room(p,req)
            if r:
                snapshot = self.remove_from_room(p, r)
                p.send('LEAVE_ROOM_RESPONSE',{'success':True},req)
                if snapshot is not None:
                    self.broadcast(r, 'PLAYER_STATUS_EVENT', snapshot)
        elif typ=='LOGOUT_REQUEST':
            p.send('LOGOUT_RESPONSE',{'success':True},req); self.drop(p)
        else: self.error(p,req,'UNKNOWN_COMMAND',f'Unsupported message type: {typ}')
    def get_room(self,p,req):
        if not p.room: self.error(p,req,'NOT_IN_ROOM','Join or create a room first'); return None
        with self.lock: r=self.rooms.get(p.room)
        if not r: self.error(p,req,'ROOM_NOT_FOUND','Room no longer exists'); return None
        return r
    @staticmethod
    def leaderboard(r):
        return sorted([{'user_id':uid,'name':p.name,'score':r.scores.get(uid,0)} for uid,p in r.players.items()],key=lambda x:(-x['score'],x['name'].casefold(),x['user_id']))
    def play(self,r):
        try:
            self.broadcast(r,'QUIZ_STARTED_EVENT',{'quiz_id':r.quiz['quiz_id'],'title':r.quiz['title'],'total_questions':len(r.quiz['questions'])})
            for index,q in enumerate(r.quiz['questions'],1):
                with r.lock:
                    if not r.players: break
                    r.current_q=q; r.answers={}; r.deadline=time.monotonic()+q['time_limit']; players=list(r.players.values())
                payload={'question_id':q['question_id'],'number':index,'text':q['text'],'options':q['options'],'time_limit':q['time_limit'],'points':q['points']}
                for p in players:
                    try: p.send('QUESTION_EVENT',payload,event=True)
                    except OSError: self.drop(p)
                while time.monotonic() < r.deadline:
                    with r.lock:
                        active=set(r.players); answered=set(r.answers)
                        if active and active.issubset(answered): break
                    time.sleep(0.05)
                with r.lock:
                    answer_copy=dict(r.answers); active=list(r.players.values())
                    for p in active:
                        if answer_copy.get(p.user_id)==q['answer']: r.scores[p.user_id]=r.scores.get(p.user_id,0)+q['points']
                    r.current_q=None; r.answers={}; board=self.leaderboard(r)
                result={'question_id':q['question_id'],'correct_answer':q['answer'],'answers':answer_copy,'points_awarded':{player.user_id:(q['points'] if answer_copy.get(player.user_id)==q['answer'] else 0) for player in active},'leaderboard':board}
                self.broadcast(r,'QUESTION_RESULT_EVENT',result)
                time.sleep(1)
            with r.lock:
                r.state='FINISHED'; board=self.leaderboard(r); winner=board[0]['user_id'] if board else None
            self.broadcast(r,'QUIZ_FINISHED_EVENT',{'quiz_id':r.quiz['quiz_id'],'final_leaderboard':board,'winner':winner})
        except Exception as e:
            print(f'Room {r.code} error: {e}',file=sys.stderr)
            with r.lock: r.state='FINISHED'
    def serve(self):
        self.listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM); self.listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        self.listener.bind((self.host,self.port)); self.listener.listen(50); self.listener.settimeout(1)
        print('SERVER_READY',flush=True)
        try:
            while not self.stopping.is_set():
                try: sock,addr=self.listener.accept()
                except socket.timeout: continue
                p=Player(sock,addr); threading.Thread(target=self.handle,args=(p,),daemon=True).start()
        except KeyboardInterrupt: print('\nShutting down server...',flush=True)
        finally:
            self.stopping.set()
            try: self.listener.close()
            except OSError: pass
            with self.lock: clients=list(self.players.values())
            for p in clients: self.drop(p)
            print('SERVER_STOPPED',flush=True)

def main():
    ap=argparse.ArgumentParser(description='CSI201 networked quiz tournament server')
    ap.add_argument('--host',required=True); ap.add_argument('--port',required=True,type=int); ap.add_argument('--questions',required=True)
    a=ap.parse_args()
    if not 1 <= a.port <= 65535: ap.error('--port must be 1-65535')
    try: quizzes=load_questions(a.questions)
    except (OSError,ValueError) as e: print(f'QUESTION_BANK_ERROR: {e}',file=sys.stderr); return 2
    try: Server(a.host,a.port,quizzes).serve()
    except OSError as e: print(f'SERVER_ERROR: {e}',file=sys.stderr); return 1
    return 0
if __name__=='__main__': raise SystemExit(main())
