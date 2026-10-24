#!/usr/bin/env python3
"""Omarchy setup PoC. External Pilot release only; never vendors collector code.

probe/plan are read-only. apply requires the exact current plan digest.
Fresh installs only; existing collector configuration is never rewritten.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request

VERSION = "1.13.0"
COMMIT = "2b516fb8423924c7541b89d9b8e30f61e0dbaff8"
ASSETS = {
    "installer.sh": (
        f"https://raw.githubusercontent.com/alibaba/loongsuite-pilot/{COMMIT}/deploy/installer-opensource.sh",
        "01fcc760b6ee4fa876e9b5755b1f934536fd9fb93a99f17d7fb9bda9aebd4295"),
    "pilot.tar.gz": (
        f"https://loongcollector-community-edition.oss-cn-shanghai.aliyuncs.com/loongsuite-pilot/{VERSION}/loongsuite-pilot.tar.gz",
        "16b6d06b915c73b0b5ac29668a4c219b9d6589240cc66b4e134e5fa3b153440f"),
}


class SetupError(Exception):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_object(path):
    if path.stat().st_size > 1024 * 1024:
        raise SetupError("Configuration exceeds the 1 MiB read limit.")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise SetupError("Expected a JSON object.")
    return value


def fingerprint(path):
    if not path.exists():
        return "missing"
    try:
        if path.is_file() and path.stat().st_size < 1024 * 1024:
            return digest(path.read_bytes())
    except OSError:
        pass
    return "unreadable"


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".setup-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(value, f, indent=2)
            f.write("\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class Setup:
    def __init__(self, home=None, env=None, system=None):
        self.env = dict(os.environ if env is None else env)
        self.home = Path(home or Path.home())
        self.system = system or platform.system()
        self.data = Path(self.env.get("LOONGSUITE_PILOT_DATA_DIR", str(self.home / ".loongsuite-pilot"))).expanduser()
        self.cache_root = Path(self.env.get("LOONGSUITE_PILOT_CACHE_DIR", str(self.home / ".loongsuite-pilot"))).expanduser()
        self.config_home = Path(self.env.get("XDG_CONFIG_HOME", str(self.home / ".config")))
        self.panel_config = self.config_home / "omarchy/pilot.json"
        self.cache = Path(self.env.get("XDG_CACHE_HOME", str(self.home / ".cache"))) / "omarchy-agent-activity"
        self.config = self.data / "config.json"

    def cli(self):
        local = self.home / ".local/bin/loongsuite-pilot"
        if local.is_file() and os.access(local, os.X_OK):
            return str(local)
        return shutil.which("loongsuite-pilot", path=self.env.get("PATH", "")) or ""

    def installed_version(self):
        candidates = [self.cache_root / "package/package.json"]
        current = self.cache_root / "current"
        if current.is_file() and current.stat().st_size < 256:
            name = current.read_text().strip()
            if re.fullmatch(r"[0-9A-Za-z._-]+", name) and ".." not in name:
                candidates.insert(0, self.cache_root / "versions" / name / "package.json")
        for p in candidates:
            if p.is_file():
                try:
                    obj = read_object(p)
                    if obj.get("name") == "loongsuite-pilot":
                        return str(obj.get("version", ""))
                except (ValueError, OSError, SetupError):
                    pass
        return ""

    def runtime_status(self):
        try:
            pid = int((self.data / "loongsuite-pilot.pid").read_text().strip())
            if pid < 2:
                return "unknown"
            os.kill(pid, 0)
            cmd = Path(f"/proc/{pid}/cmdline")
            if cmd.is_file():
                text = cmd.read_bytes().decode(errors="replace")
                return "running" if "loongsuite" in text or "collector-daemon" in text else "unknown"
            return "unknown"
        except (OSError, ValueError):
            return "not detected"

    def fresh_prerequisites(self):
        if self.system != "Linux":
            return "Installation requires Linux with a running Omarchy user session."
        if os.getuid() == 0:
            return "Run setup as the desktop user, not root."
        if self.data != self.home / ".loongsuite-pilot" or self.cache_root != self.data:
            return "Custom Pilot paths are read-only in this PoC."
        # The pinned upstream installer interpolates HOME into shell/JS snippets.
        if not re.fullmatch(r"/[A-Za-z0-9_./-]+", str(self.home)):
            return "This PoC installer does not support special characters in the home path."
        for cmd in ("bash", "curl", "tar", "systemctl", "omarchy-shell"):
            if not shutil.which(cmd, path=self.env.get("PATH", "")):
                return f"Required command missing: {cmd}"
        try:
            r = subprocess.run(["systemctl", "--user", "show-environment"], env=self.env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            if r.returncode:
                return "A working systemd user session is required."
        except (OSError, subprocess.TimeoutExpired):
            return "Cannot check the systemd user session."
        return ""

    def probe(self):
        cli, version = self.cli(), self.installed_version()
        cfg, error = {}, ""
        if self.config.exists():
            try:
                cfg = read_object(self.config)
            except (OSError, ValueError, SetupError):
                error = "Pilot configuration cannot be read. No files will be overwritten."
        else:
            error = "Pilot configuration is missing." if cli or version else ""
        agents = cfg.get("agents", {})
        agents = agents if isinstance(agents, dict) else {}
        policies = [v.get("captureMessageContent") for v in agents.values()
                    if isinstance(v, dict) and v.get("enabled") is not False]
        capture = "off" if policies and all(v is False for v in policies) else "on or unspecified"
        jsonl = cfg.get("jsonl") or {}
        if not isinstance(jsonl, dict):
            error, jsonl = "Unsupported JSONL configuration.", {}
        output = str(jsonl.get("outputDir") or self.data / "logs/output")
        if output.startswith("~/"):
            output = str(self.home / output[2:])
        if not Path(output).is_absolute():
            error = "Relative JSONL output paths need manual configuration."
        remote = []
        for k in ("sls", "http", "otlp", "cms"):
            if cfg.get(k):
                settings = cfg[k]
                disabled = (isinstance(settings, dict) and settings.get("enabled") is False)
                disabled = disabled or (k == "sls" and cfg.get("collectLog") is False)
                disabled = disabled or (k in ("otlp", "cms") and cfg.get("collectTrace") is False)
                remote.append(k + (": disabled" if disabled else ": configured (review in Pilot)"))
        evidence = self.data.exists() and (self.data.is_symlink() or any(self.data.iterdir()))
        if error:
            state = "needs-review"
        elif cli and version == VERSION:
            state = "existing"
        elif cli or version:
            state, error = "incompatible", f"PoC verified version: {VERSION}. Existing version: {version or 'unknown'}."
        elif evidence or self.cache_root.exists() and any(self.cache_root.iterdir()):
            state, error = "needs-review", "An incomplete or custom Pilot installation exists. Repair it manually; setup will not overwrite it."
        else:
            state = "missing"
        if state == "existing" and jsonl.get("enabled") is False:
            state, error = "needs-review", "Pilot local JSONL output is disabled. Existing configuration is preserved."
        return {
            "state": state, "message": error, "version": version, "supportedVersion": VERSION,
            "cli": cli, "dataDir": str(self.data), "outputDir": output,
            "service": self.runtime_status() if cli else "not installed",
            "capture": capture if cfg else "unknown", "remote": ", ".join(remote) or "none configured in this file",
            "configHash": fingerprint(self.config), "panelHash": fingerprint(self.panel_config),
            "source": "Existing configuration inspected; environment overrides are not audited.",
        }

    def plan(self):
        observed = self.probe()
        action, message = "none", observed["message"]
        if observed["state"] == "existing":
            action, message = "connect", "Connect this panel to existing JSONL. Pilot configuration and services stay unchanged."
        elif observed["state"] == "missing":
            message = self.fresh_prerequisites()
            if not message:
                action, message = "install", "Install the official Pilot release, configure Codex usage-only collection, and start its user services."
        value = {"action": action, "message": message, "observed": observed,
                 "version": VERSION, "agents": ["codex"], "contentCapture": False,
                 "assets": ASSETS if action == "install" else {},
                 "effects": ["Download Pilot and any required Node runtime/dependencies",
                             "Write usage-only configuration BEFORE starting collection",
                             "Deploy Codex integration and start Pilot user services",
                             "Official installer may add its CLI to your shell PATH",
                             "Local JSONL only; auto-update disabled for this PoC"] if action == "install"
                            else ["Write the panel data path only; preserve existing presentation preferences"]}
        # Dynamic process status does not change what has been approved.
        stable = json.loads(json.dumps(value))
        stable["observed"].pop("service", None)
        value["token"] = digest(json.dumps(stable, sort_keys=True).encode())
        return value

    def download(self, name):
        url, checksum = ASSETS[name]
        path = self.cache / name
        if path.is_file() and digest(path.read_bytes()) == checksum:
            return path
        fd, temp = tempfile.mkstemp(dir=self.cache)
        try:
            with os.fdopen(fd, "wb") as out, urllib.request.urlopen(url, timeout=30) as response:
                if not response.url.startswith("https://"):
                    raise SetupError("Refusing a non-HTTPS download redirect.")
                total = 0
                while chunk := response.read(65536):
                    total += len(chunk)
                    if total > 64 * 1024 * 1024:
                        raise SetupError("Download exceeds the 64 MiB limit.")
                    out.write(chunk)
            if digest(Path(temp).read_bytes()) != checksum:
                raise SetupError("Download checksum mismatch. Nothing was installed.")
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        return path

    def seed_config(self):
        return {"enabled": True, "dataDir": str(self.data), "collectLog": False, "collectTrace": False,
                "jsonl": {"enabled": True, "outputDir": str(self.data / "logs/output")},
                "http": {"enabled": False}, "autoUpdate": {"enabled": False},
                "enableStatusBarApp": False, "agents": {"codex": {"enabled": True, "captureMessageContent": False}},
                "mask": {"mode": "all"}}

    def run_installer(self, installer, package, log):
        # Do not let parent environment inject backend credentials or Node preload hooks.
        allowed = ("HOME", "USER", "LOGNAME", "PATH", "LANG", "LC_ALL", "TERM", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS")
        env = {k: v for k, v in self.env.items() if k in allowed}
        env.update(HOME=str(self.home), LOONGSUITE_PILOT_AUTO_UPDATE_ENABLED="false")
        command = ["bash", str(installer), "install", "--version", VERSION,
                   "--package-url", package.as_uri(), "--agents", "codex",
                   "--collect-log", "false", "--collect-trace", "false", "--lang", "en",
                   "--enable-status-bar-app", "false", "--multimodal-mode", "none"]
        with log.open("w") as out:
            os.chmod(log, 0o600)
            result = subprocess.run(command, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT)
        if result.returncode:
            raise SetupError(f"Official installer exited {result.returncode}. Check the local installation log; partial installation is preserved for inspection.")

    def connect(self, observed):
        cfg = read_object(self.panel_config) if self.panel_config.exists() else {"allowContent": False}
        cfg.update(outputDir=observed["outputDir"], provenance=f"Local LoongSuite Pilot {observed['version']}")
        if self.panel_config.exists():
            previous = read_object(self.panel_config)
            if previous == cfg:
                return
            shutil.copy2(self.panel_config, self.panel_config.with_name(f"pilot.json.backup-{time.time_ns()}"))
        atomic_json(self.panel_config, cfg)

    def apply(self, token):
        self.cache.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self.cache / "setup.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise SetupError("Another setup is already running.")
            plan = self.plan()
            if token != plan["token"]:
                raise SetupError("Environment changed since review. Refresh and review the new plan.")
            if plan["action"] == "none":
                raise SetupError(plan["message"] or "No setup action is available.")
            if plan["action"] == "connect":
                self.connect(plan["observed"])
                return {"ok": True, "message": "Connected. Existing Pilot configuration and services were not changed.", "probe": self.probe()}
            installer = self.download("installer.sh")
            package = self.download("pilot.tar.gz")
            # Recheck after network I/O; never clobber an installation created meanwhile.
            if self.plan()["token"] != token:
                raise SetupError("Environment changed during download. Review again.")
            self.data.mkdir(mode=0o700, exist_ok=True)
            with self.config.open("x") as f:
                os.chmod(self.config, 0o600)
                json.dump(self.seed_config(), f, indent=2)
            atomic_json(self.cache / "attempt.json", {"stage": "starting", "time": time.time(), "version": VERSION})
            log = self.cache / "install.log"
            try:
                self.run_installer(installer, package, log)
                now = self.probe()
                if now["state"] != "existing" or now["capture"] != "off":
                    raise SetupError("Post-install checks failed; inspect configuration before using collection.")
                cfg = read_object(self.config)
                if cfg.get("collectLog") is not False or cfg.get("collectTrace") is not False or cfg.get("http", {}).get("enabled") is not False:
                    raise SetupError("Post-install local-output policy check failed.")
                if now["service"] != "running":
                    raise SetupError("Pilot was installed but its running collector was not verified. Inspect the log before retrying.")
                self.connect(now)
                atomic_json(self.cache / "attempt.json", {"stage": "complete", "time": time.time(), "version": VERSION})
                return {"ok": True, "message": "Pilot installed. Codex content capture is off; local output is ready.", "probe": now}
            except Exception:
                atomic_json(self.cache / "attempt.json", {"stage": "failed", "time": time.time(), "log": str(log)})
                raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["probe", "plan", "apply"])
    parser.add_argument("--token", default="")
    args = parser.parse_args()
    try:
        setup = Setup()
        result = setup.apply(args.token) if args.action == "apply" else getattr(setup, args.action)()
        print(json.dumps(result))
    except Exception as e:
        # Never emit raw upstream configuration or subprocess output to the panel.
        message = str(e) if isinstance(e, SetupError) else "Setup failed. Check permissions, network access and the local setup log."
        print(json.dumps({"ok": False, "message": message}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
