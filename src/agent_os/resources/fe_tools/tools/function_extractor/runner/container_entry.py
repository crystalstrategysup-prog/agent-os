"""Fixed offline container entry. Inputs are frozen code and synthetic fixtures."""
import json
from pathlib import Path
import sys

sys.path.insert(0, "/opt/fe")
from tools.function_extractor.runner.bundle import materialize_bundle
from tools.function_extractor.runner.loader import load_engine

with materialize_bundle(Path(sys.argv[1])) as bundle:
    fixture = json.loads(Path(sys.argv[2]).read_bytes())
    if len(sys.argv) not in (4, 6):
        raise ValueError('container_entry_arguments')
    extra = {} if len(sys.argv) == 4 else {'contract_plan': json.loads(Path(sys.argv[4]).read_bytes()),
                                         'runner_sha256': sys.argv[5]}
    result = load_engine("route_probe_replay").replay_bundle(bundle, fixture, timeout=float(sys.argv[3]), **extra)
    status = {}
    for line in Path("/proc/self/status").read_text().splitlines():
        key, _, value = line.partition(":")
        if key in {"Uid", "Gid", "CapEff", "NoNewPrivs", "Seccomp"}:
            status[key] = value.strip()
    result["container_effective"] = {"uid": int(status["Uid"].split()[0]), "gid": int(status["Gid"].split()[0]),
                                     "cap_eff": status["CapEff"], "no_new_privs": int(status["NoNewPrivs"]),
                                     "seccomp": int(status["Seccomp"]),
                                     "interfaces": sorted(p.name for p in Path("/sys/class/net").iterdir()),
                                     "root_readonly": not any(line.split()[1] == "/" and "rw" in line.split()[3].split(",")
                                                          for line in Path("/proc/mounts").read_text().splitlines())}
    print(json.dumps(result, separators=(",", ":")))
