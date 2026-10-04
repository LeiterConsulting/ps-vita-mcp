"""Real heartbeat HTTP with a simulated Vita endpoint; no hardware acceptance."""
import json,os,sys,tempfile,threading,time,unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from workbench.power import WorkKeeper,pack
from workbench.session import exclusive
from resident.control.bridge_tools import ControlClient

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name);self.calls=[];self.lost=False
        os.environ['VITA_WORKBENCH_LOCK']=str(self.folder/'lock')
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                self.send({'app':'Vita Control','version':'0.3.0','abi':2,'build_id':'a'*64,'power_protocol':1})
            def do_POST(self):
                import struct
                body=self.rfile.read(int(self.headers['Content-Length']));ttl=struct.unpack('<5I',body)[2];owner.calls.append(ttl)
                if owner.lost and ttl:self.close_connection=True;return
                self.send({'app':'Vita Work Power','abi':2,'lease_remaining_ms':ttl,'dimmed':False})
            def send(self,value):
                raw=json.dumps(value).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=self.server.serve_forever,daemon=True).start()
        os.environ['VITA_CONTROL_PORT']=str(self.server.server_port)
        self.client=ControlClient(lambda:{'host':'127.0.0.1','port':self.server.server_port-1,'token':'d'*32})
    def tearDown(self):self.server.shutdown();self.server.server_close();self.temp.cleanup()
    def test_background_renewal_under_exclusive_job_and_cleanup(self):
        with exclusive():
            keeper=WorkKeeper(self.client,self.folder,interval=.05);keeper.start({'abi':2,'power_protocol':1})
            limit=time.monotonic()+2
            while len(self.calls)<3 and time.monotonic()<limit:time.sleep(.01)
            result=keeper.stop()
        self.assertGreaterEqual(result['renewals'],2);self.assertEqual(self.calls[-1],0)
        events=[json.loads(x) for x in (self.folder/'power.jsonl').read_text().splitlines()]
        self.assertEqual([e['kind'] for e in events],['lease_intent','lease_receipt']*(len(events)//2))
    def test_lost_heartbeat_stops_without_replay(self):
        with exclusive():
            keeper=WorkKeeper(self.client,self.folder,interval=.05);keeper.start({'abi':2,'power_protocol':1});self.lost=True
            self.assertTrue(keeper.end.wait(2));count=len(self.calls);time.sleep(.15);self.assertEqual(len(self.calls),count)
            result=keeper.stop()
        self.assertEqual(self.calls,[30000,30000,0]);self.assertEqual(len(result['errors']),1)
    def test_read_only_status_and_legacy_do_not_enable_work(self):
        self.client.status();self.assertEqual(self.calls,[])
        keeper=WorkKeeper(self.client,self.folder);keeper.start({'abi':1});self.assertFalse(keeper.stop()['enabled']);self.assertEqual(self.calls,[])
    def test_policy_types_and_bounds_before_requests(self):
        for values in [(True,30000,20),(4999,30000,20),(30001,30000,20),(30000,0,20),(30000,30000,100)]:
            with self.assertRaises(ValueError):pack(*values)
        self.assertEqual(len(pack(0)),20);self.assertEqual(self.calls,[])
    def test_control_work_renews_at_most_once_per_ten_seconds(self):
        self.client.request('GET','/workspace/list/0')
        self.assertEqual(self.calls,[30000])
        self.client.request('GET','/workspace/list/0');self.client.status()
        self.assertEqual(self.calls,[30000])
        self.client.work_renewed-=11;self.client.request('GET','/workspace/list/0')
        self.assertEqual(self.calls,[30000,30000])
    def test_uncertain_automatic_work_lease_stops_requested_operation(self):
        self.client.status();self.lost=True
        with self.assertRaises(RuntimeError):self.client.request('POST','/input',b'not submitted')
        self.assertEqual(self.calls,[30000])
if __name__=='__main__':unittest.main(verbosity=2)
