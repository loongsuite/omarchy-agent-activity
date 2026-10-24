# Agent Activity for Omarchy

See your coding agent's usage and revisit its work, right from the Omarchy bar.
Powered by [LoongSuite Pilot](https://github.com/alibaba/loongsuite-pilot).

## See your usage

Switch between **Today**, **7 days**, and **30 days** to explore token usage,
cache reuse, daily trends, and the models you use.

## Follow a session

Browse your sessions, see their duration, turns, and token usage, then open one
to follow the conversation and inspect tool results. Costs appear when reported
by the source. Press **Backspace** or **Esc** to return to the session list.

## Install

Requires the Omarchy Quattro desktop, Python 3, Git, `curl`, `tar`, and a running
systemd user session. Currently supports Codex with LoongSuite Pilot 1.13.0.

Open a terminal in Omarchy and run:

```sh
git clone https://github.com/loongsuite/omarchy-agent-activity.git
cd omarchy-agent-activity
bash install.sh
```

1. Click the **chart icon** in the top bar.
2. Open **Setup** and select **Review setup**.
3. Choose **Install & set up Pilot**, or **Connect existing Pilot** if a
   compatible installation is already available. Keep the desktop running
   until setup completes.
4. Use Codex, then open **Overview** or **Sessions** and click **Refresh** to
   see the recorded activity.

## Your data

The panel reads local records. New installations disable message-content
capture and remote export by default; existing Pilot settings are preserved.
Conversation details require content collection and display to be enabled.
These settings do not delete transcripts already stored by your coding agent.

Usage reflects available local records, not your account quota or billing total.

## License

[Apache License 2.0](LICENSE). See [NOTICE](NOTICE) and
[THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES) for third-party attribution.
LoongSuite Pilot is installed separately and retains its own license.
