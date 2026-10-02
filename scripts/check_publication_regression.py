"""Demonstrate that the host regression fails without the observed publication repair."""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
source = (ROOT/"devloop/server_vita.c").read_text()
marker = "        server.snapshot=*c;\n        server.pending=2;"
assert source.count(marker)==1
legacy = source.replace(marker,"        server.pending=2;")
path = ROOT/"build/host/server-before-publication-fix.c"
path.write_text(legacy)
image = json.loads((ROOT/"toolchain.lock.json").read_text())["image"]
command = "cc -std=c11 -Wall -Wextra -Werror -Wno-unused-parameter -fsanitize=address,undefined -g -Icommon -Idevloop -Itests -Ithird_party/lua-5.4.9/src -DDEVLOOP_SERVER_SOURCE='\"/workspace/build/host/server-before-publication-fix.c\"' tests/test_server_vita_host.c devloop/core.c devloop/script_runtime.c devloop/sha256.c tests/render_stub.c common/physics.c common/math_helpers.c build/host/libdevloop_lua.a -pthread -lm -o build/host/test_server_before_fix && build/host/test_server_before_fix"
result = subprocess.run(["docker","run","--rm","--network","none","--mount",f"type=bind,source={ROOT},target=/workspace",image,"sh","-c",command],capture_output=True,text=True)
log = result.stdout+result.stderr
(ROOT/"evidence/devloop/publication-before-fix.log").write_text(log)
assert result.returncode==134 and 'strstr(reply,"\\\"revision\\\":2")' in log, log
report = {"checkedUtc":datetime.now(timezone.utc).isoformat(),"test":"Actual native-server host harness with only command snapshot publication removed", "expectedFailureObserved":True,"exitCode":result.returncode,"failure":"Immediate status did not contain acknowledged revision 2/frame 41", "modifiedSourceSha256":hashlib.sha256(legacy.encode()).hexdigest(),"repairedSourceSha256":hashlib.sha256(source.encode()).hexdigest(),"repairedHarness":"passed: 1001 forced command/status pairs in host-tests.log", "physicalAcceptance":"separate; see version-bound live evidence"}
(ROOT/"evidence/devloop/publication-regression.json").write_text(json.dumps(report,indent=2)+"\n")
print("PASS regression sensitivity: removing the publication repair reproduces the stale revision assertion (expected abort 134).")
