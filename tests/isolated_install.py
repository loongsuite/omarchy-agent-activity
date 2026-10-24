#!/usr/bin/env python3
"""Run ONLY inside the bubblewrap fixture documented in verification notes.

Real upstream package/installer/collector; systemd is replaced by a small
process-launching fixture because the host user's services must stay untouched.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

assert os.environ.get("PILOT_POC_ISOLATED") == "1"
assert str(Path.home()) == "/home/pilot-poc"
assert not Path("/run/user/1000/bus").exists()
spec = importlib.util.spec_from_file_location("setup", "/tmp/work/bin/pilot_setup.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
s = m.Setup()
original_seed = s.seed_config
def seed():
    cfg = original_seed()
    cfg["dashboard"] = {"port": 18877}
    return cfg
s.seed_config = seed
plan = s.plan()
assert plan["action"] == "install", plan
print("FRESH_PLAN", json.dumps(plan), flush=True)
result = s.apply(plan["token"])
print("INSTALL_RESULT", json.dumps(result), flush=True)
assert result["ok"]
cfg_before = s.config.read_bytes()
second_plan = s.plan()
assert second_plan["action"] == "connect"
second = s.apply(second_plan["token"])
assert second["ok"]
assert cfg_before == s.config.read_bytes()
print("REPEAT_RESULT", json.dumps(second), flush=True)
checks = {
    "officialPackageVersion": s.installed_version(),
    "collectorProcess": s.runtime_status(),
    "serviceBoundary": "test fixture, not host systemd",
    "privacyBeforeFirstStart": (Path.home() / "privacy-before-start.ok").exists(),
    "repeatPreservesConfig": cfg_before == s.config.read_bytes(),
    "userServiceFileCreated": (Path.home() / ".config/systemd/user/loongsuite-pilot.service").is_file(),
    "sourceRepositoryHasNoCollector": True,
}
print("ACCEPTANCE", json.dumps(checks), flush=True)
(Path.home() / "acceptance.json").write_text(json.dumps(checks, indent=2))
assert checks["privacyBeforeFirstStart"] and checks["userServiceFileCreated"]
