import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("pilot_setup", Path(__file__).parents[1] / "bin/pilot_setup.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.s = m.Setup(home=self.home, env={"HOME": str(self.home), "PATH": "/usr/bin:/bin"}, system="Linux")
        self.s.fresh_prerequisites = lambda: ""

    def tearDown(self):
        self.tmp.cleanup()

    def existing(self, version=m.VERSION, **extra):
        p = self.s.cache_root / "versions" / (version + "_build")
        p.mkdir(parents=True)
        (p / "package.json").write_text(json.dumps({"name": "loongsuite-pilot", "version": version}))
        (self.s.cache_root / "current").write_text(version + "_build")
        cli = self.home / ".local/bin/loongsuite-pilot"
        cli.parent.mkdir(parents=True)
        cli.write_text("#!/bin/sh\nexit 99\n")
        cli.chmod(0o700)
        cfg = self.s.seed_config()
        cfg.update(extra)
        self.s.config.write_text(json.dumps(cfg))

    def test_probe_and_plan_are_read_only(self):
        self.assertEqual(self.s.probe()["state"], "missing")
        self.assertEqual(self.s.plan()["action"], "install")
        self.assertEqual(list(self.home.iterdir()), [])

    def test_existing_connect_preserves_collector_and_panel_preferences(self):
        self.existing(agents={"codex": {"captureMessageContent": True}}, sls={"apiKey": "secret-test"})
        before = self.s.config.read_bytes()
        m.atomic_json(self.s.panel_config, {"allowContent": True, "excludedSessionIds": ["private-id"]})
        plan = self.s.plan()
        self.assertEqual(plan["action"], "connect")
        self.assertNotIn("secret-test", json.dumps(plan))
        self.assertIn("sls", plan["observed"]["remote"])
        with patch.object(self.s, "run_installer", side_effect=AssertionError("must not install")):
            self.s.apply(plan["token"])
        self.assertEqual(before, self.s.config.read_bytes())
        cfg = m.read_object(self.s.panel_config)
        self.assertTrue(cfg["allowContent"])
        self.assertEqual(cfg["excludedSessionIds"], ["private-id"])
        backups = list(self.s.panel_config.parent.glob("*.backup-*"))
        self.assertEqual(len(backups), 1)
        self.s.apply(self.s.plan()["token"])
        self.assertEqual(len(list(self.s.panel_config.parent.glob("*.backup-*"))), 1)

    def test_stale_plan_rejected_without_config_overwrite(self):
        self.existing()
        plan = self.s.plan()
        self.s.config.write_text('{"enabled":false}')
        with self.assertRaisesRegex(m.SetupError, "Environment changed"):
            self.s.apply(plan["token"])
        self.assertFalse(self.s.panel_config.exists())
        self.assertEqual(self.s.config.read_text(), '{"enabled":false}')

    def test_unknown_version_is_never_reinstalled(self):
        self.existing(version="99.0.0")
        plan = self.s.plan()
        self.assertEqual(plan["action"], "none")
        with self.assertRaises(m.SetupError):
            self.s.apply(plan["token"])

    def test_partial_install_is_preserved(self):
        self.s.data.mkdir()
        (self.s.data / "unfinished").write_text("keep")
        self.assertEqual(self.s.plan()["action"], "none")
        self.assertEqual((self.s.data / "unfinished").read_text(), "keep")

    def test_corrupt_config_and_disabled_output_need_review(self):
        self.existing(jsonl={"enabled": False})
        self.assertEqual(self.s.plan()["action"], "none")
        self.s.config.write_text("{")
        self.assertEqual(self.s.plan()["action"], "none")

    def fake_install(self, installer, package, log):
        # This is the boundary immediately BEFORE upstream starts anything.
        cfg = m.read_object(self.s.config)
        self.assertFalse(cfg["agents"]["codex"]["captureMessageContent"])
        self.assertFalse(cfg["collectLog"])
        self.assertFalse(cfg["collectTrace"])
        self.assertFalse(cfg["http"]["enabled"])
        self.assertFalse(cfg["autoUpdate"]["enabled"])
        self.assertEqual(self.s.config.stat().st_mode & 0o777, 0o600)
        p = self.s.cache_root / "package"
        p.mkdir()
        (p / "package.json").write_text(json.dumps({"name": "loongsuite-pilot", "version": m.VERSION}))
        c = self.home / ".local/bin/loongsuite-pilot"
        c.parent.mkdir(parents=True)
        c.write_text("#!/bin/sh\nexit 0\n")
        c.chmod(0o700)

    def test_fresh_install_privacy_precedes_first_start(self):
        plan = self.s.plan()
        with patch.object(self.s, "download", return_value=self.home / "asset"), \
             patch.object(self.s, "run_installer", side_effect=self.fake_install), \
             patch.object(self.s, "runtime_status", return_value="running"):
            result = self.s.apply(plan["token"])
        self.assertTrue(result["ok"])
        self.assertFalse(m.read_object(self.s.panel_config)["allowContent"])
        self.assertEqual(self.s.plan()["action"], "connect")

    def test_download_failure_does_not_create_pilot_config(self):
        plan = self.s.plan()
        with patch.object(self.s, "download", side_effect=m.SetupError("Download failed")):
            with self.assertRaisesRegex(m.SetupError, "Download failed"):
                self.s.apply(plan["token"])
        self.assertFalse(self.s.config.exists())

    def test_changed_environment_during_download_aborts(self):
        plan = self.s.plan()
        def race(name):
            if not self.s.config.exists():
                self.existing()
            return self.home / name
        with patch.object(self.s, "download", side_effect=race), \
             patch.object(self.s, "run_installer", side_effect=AssertionError("must not run")):
            with self.assertRaisesRegex(m.SetupError, "Environment changed"):
                self.s.apply(plan["token"])

    def test_installer_failure_retains_config_and_reports_partial_state(self):
        plan = self.s.plan()
        with patch.object(self.s, "download", return_value=self.home / "asset"), \
             patch.object(self.s, "run_installer", side_effect=m.SetupError("upstream failed")):
            with self.assertRaises(m.SetupError):
                self.s.apply(plan["token"])
        self.assertTrue(self.s.config.exists())
        self.assertFalse(self.s.panel_config.exists())
        self.assertEqual(m.read_object(self.s.cache / "attempt.json")["stage"], "failed")
        self.assertEqual(self.s.plan()["action"], "none")

    def test_parallel_apply_is_refused(self):
        self.s.cache.mkdir(parents=True)
        with (self.s.cache / "setup.lock").open("a") as lock:
            m.fcntl.flock(lock, m.fcntl.LOCK_EX | m.fcntl.LOCK_NB)
            with self.assertRaisesRegex(m.SetupError, "already running"):
                self.s.apply(self.s.plan()["token"])

    def test_checksum_failure_never_executes_download(self):
        self.s.cache.mkdir(parents=True)
        response = io.BytesIO(b"unexpected upstream bytes")
        response.url = "https://example.invalid/asset"
        with patch.object(m.urllib.request, "urlopen", return_value=response):
            with self.assertRaisesRegex(m.SetupError, "checksum mismatch"):
                self.s.download("installer.sh")
        self.assertFalse((self.s.cache / "installer.sh").exists())

    def test_successful_cached_artifact_avoids_network(self):
        self.s.cache.mkdir(parents=True)
        content = b"fixture only"
        (self.s.cache / "installer.sh").write_bytes(content)
        with patch.dict(m.ASSETS, {"installer.sh": ("https://example.invalid", hashlib.sha256(content).hexdigest())}), \
             patch.object(m.urllib.request, "urlopen", side_effect=AssertionError("must not download")):
            self.assertEqual(self.s.download("installer.sh").read_bytes(), content)


if __name__ == "__main__":
    unittest.main()
