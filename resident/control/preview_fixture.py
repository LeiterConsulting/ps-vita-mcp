"""Local simulation for browser qualification. Never connects to the Vita."""
import importlib.util
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('control_http_fixture',ROOT/'resident/control/test_bridge.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
server=ThreadingHTTPServer(('127.0.0.1',0),fixture.Device)
threading.Thread(target=server.serve_forever,daemon=True).start()
config=ROOT/'.devloop-private/control-preview-fixture.json'
config.write_text(json.dumps({'host':'127.0.0.1','port':17866,'token':fixture.TOKEN}),encoding='utf-8')
os.environ['VITA_RESIDENT_CONFIG']=str(config);os.environ['VITA_CONTROL_PORT']=str(server.server_port)
import preview
print('BROWSER FIXTURE: simulated RGB/input; no physical Vita connection',flush=True)
preview.serve(0)
