import json, socket, struct, sys, threading, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))
from server import recv_message, send_message

class FramingTests(unittest.TestCase):
    def setUp(self):
        self.rx, self.tx = socket.socketpair()
        self.lock = threading.Lock()
    def tearDown(self):
        self.rx.close(); self.tx.close()
    def test_fragmented_frame(self):
        payload=json.dumps({'type':'PING','payload':{'x':1}}).encode()
        frame=struct.pack('!I',len(payload))+payload
        def writer():
            for part in (frame[:2],frame[2:5],frame[5:]):
                self.tx.sendall(part)
        t=threading.Thread(target=writer);t.start()
        self.assertEqual(recv_message(self.rx)['type'],'PING')
        t.join()
    def test_two_coalesced_frames(self):
        send_message(self.tx,self.lock,{'type':'ONE'})
        send_message(self.tx,self.lock,{'type':'TWO'})
        self.assertEqual(recv_message(self.rx)['type'],'ONE')
        self.assertEqual(recv_message(self.rx)['type'],'TWO')
    def test_zero_length_frame_rejected(self):
        self.tx.sendall(struct.pack('!I',0))
        with self.assertRaises(ValueError): recv_message(self.rx)

if __name__=='__main__': unittest.main()
