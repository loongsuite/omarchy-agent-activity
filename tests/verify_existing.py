"""Explicit installed-VM acceptance; connects panel but must not modify Pilot."""
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("setup", Path(__file__).parents[1] / "bin/pilot_setup.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
s = m.Setup()
plan = s.plan()
assert plan["action"] == "connect", plan["message"]
before = s.config.read_bytes()
pidfile = s.data / "loongsuite-pilot.pid"
pid = pidfile.read_text()
presentation = m.read_object(s.panel_config)
r1 = s.apply(plan["token"])
assert r1["ok"]
linked = s.panel_config.read_bytes()
r2 = s.apply(s.plan()["token"])
assert r2["ok"]
assert before == s.config.read_bytes()
assert pid == pidfile.read_text()
assert linked == s.panel_config.read_bytes()
after = m.read_object(s.panel_config)
for k in ("allowContent", "excludedSessionIds"):
    assert presentation.get(k) == after.get(k)
print(json.dumps({"existingPilotReuse": True, "repeatIdempotent": True,
                  "collectorConfigUnchanged": True, "collectorPidUnchanged": True,
                  "presentationPreferencesPreserved": True, "version": plan["observed"]["version"]}))
