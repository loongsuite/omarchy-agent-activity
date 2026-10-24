# Agent Activity for Omarchy

Native local usage and session history, powered by an externally installed
LoongSuite Pilot. This repository contains no Pilot collector source or package.

**Experimental PoC** for the Omarchy Quattro desktop and Pilot 1.13.0 / Codex.
Overview shows recorded usage; Sessions lets you inspect individual conversations
and tool results when content collection and display are explicitly enabled.

## Run on Omarchy

```sh
git clone https://github.com/loongsuite/omarchy-agent-activity.git
cd omarchy-agent-activity
bash install.sh
```

Run these commands with the Quattro desktop running.
This installs only the panel. It preserves the previous plugin in
`~/.config/omarchy/pilot-backups/`. It uses the prototype's existing plugin ID so
the bar placement and existing data settings survive. The ID remains
`io.github.loongsuite.pilot` for compatibility with earlier PoC installations.

Open the chart icon, click **Setup**, then **Review setup**:

- A compatible Pilot 1.13.0 install is reused. **Connect existing Pilot** only
  updates the panel's JSONL path; it does not change capture, exports or services.
- A missing Pilot offers **Install & set up Pilot**. It downloads the official
  1.13.0 package and a commit-pinned official installer, checks their SHA-256s,
  writes usage-only configuration before starting the installer, and then invokes
  the unmodified installer with Codex selected. HTTP/SLS/trace export and automatic
  updates are explicitly disabled for a fresh install.
- Unknown versions, incomplete installs and disabled JSONL require manual review.
  There is no forced reinstall, automatic upgrade or repair in this PoC.

Fresh installation requires Linux, a working systemd user session, `curl`, `tar`,
`bash`, Python 3 and the Omarchy shell. Pilot's installer manages its runtime and
dependencies. The installer may update user shell PATH, deploy Codex integration
and start user services. Closing the panel does not cancel setup; avoid restarting
the shell during installation. This PoC's setup process is hosted by the shell.

The **reviewed plan** is checked again at apply time and after downloading. A lock
prevents simultaneous setup. Checksums pin artifacts, not a claim that the whole
dependency graph is reproducibly built: upstream may download Node/dependencies.

## Privacy and ownership

`~/.config/omarchy/pilot.json` belongs to the panel; Pilot's own `config.json`,
hooks, services and data belong to Pilot. A panel config update is backed up and
preserves existing presentation preferences and session exclusions.

Fresh installs explicitly set `agents.codex.captureMessageContent=false`. This
does not remove existing agent transcripts or guarantee that all intermediate
Pilot files exclude content. User messages, filesystem metadata and agent native
logs are different data surfaces; do not describe the entire machine as content-free.

The reader uses local files. Installation downloads require network access.
Existing collector export settings are preserved and summarized; environment
overrides and other Pilot instances are not audited. A status of **content hidden**
in the panel only describes display policy, not the collection policy.

Install logs: `~/.cache/omarchy-agent-activity/install.log` (mode 0600).
Interrupted installs are retained for inspection; rerunning refuses to overwrite
the partial collector. Plugin removal does not stop Pilot or delete its logs.

## Verification

```sh
python3 -m unittest discover -s tests -v
python3 bin/pilot_setup.py probe
python3 bin/pilot_setup.py plan
```

`probe` and `plan` do not write or download anything. `apply --token TOKEN` is a
real mutation and requires the digest returned by the latest reviewed plan.
Unit tests use isolated homes and a fake installer boundary. The normal setup
CLI has no fake-install switch. Pilot package and installer caches live outside
the plugin repository.

The PoC has also been exercised on an ARM Omarchy VM: existing Pilot reuse and
the live Setup screen were verified. A separate isolated-home test downloaded
the real official package and started its collector, but replaced systemd with
a process-launching fixture. Fresh-user installation under real systemd remains
to be verified. Scripts in `tests/verify_existing.py` and
`tests/isolated_install.py` are explicit integration checks that change state;
they are not part of the unit test command above. Do not run the fixture commands
against your normal user services.

Overview and Sessions retain bounded local reads (24 files / 16 MiB), reported
usage rather than billing or account quota, and source-reported costs only.
Unknown values are not invented. Esc / Backspace returns from a session, R reads
again. Upgrade compatibility and a permanent daemon for setup are future work.
