import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui

Panel {
  id: root
  moduleName: "io.github.loongsuite.pilot"
  manageIpc: false
  property var anchorItem: null
  property var hostWidget: null
  property var snapshot: ({items: [], status: "empty", message: "Open to inspect local activity."})
  property string failure: ""
  property string view: "overview"
  property var setupPlan: ({action: "none", observed: {}})
  property string setupOutcome: ""
  property string setupToken: ""
  Component.onCompleted: console.log("Agent Activity 0.4 setup PoC loaded", Qt.resolvedUrl(".").toString())
  readonly property color secondary: Qt.rgba(fg.r, fg.g, fg.b, 0.76)
  readonly property color fg: bar ? bar.foreground : Commons.Color.foreground
  readonly property string family: bar ? bar.fontFamily : Style.font.family
  function open() { root.controller.show(); refresh(); inspectSetup() }
  function close() { root.controller.hide() }
  function inspectSetup() { if (!setupCheck.running && !setupApply.running) setupCheck.running = true }
  function setupScript() { return decodeURIComponent(Qt.resolvedUrl("bin/pilot_setup.py").toString().replace(/^file:\/\//, "")) }
  function refresh() {
    if (reader.running) return
    failure = ""
    reader.running = true
  }
  function when(seconds) {
    return seconds ? Qt.formatDateTime(new Date(seconds * 1000), "MMM d HH:mm:ss") : "Unknown time"
  }
  function switchPanel(direction) {
    if (root.bar && typeof root.bar.switchPanelFrom === "function")
      return root.bar.switchPanelFrom(root.hostWidget || root, direction)
    return false
  }
  Process {
    id: setupCheck
    command: ["python3", root.setupScript(), "plan"]
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          var result = JSON.parse(text)
          if (!result.observed) throw new Error("No setup status")
          root.setupPlan = result
          if (result.observed.state === "missing") root.view = "setup"
        } catch (e) { root.setupOutcome = "Could not inspect Pilot. Check the local setup helper." }
      }
    }
  }
  Process {
    id: setupApply
    command: ["python3", root.setupScript(), "apply", "--token", root.setupToken]
    stdout: StdioCollector {
      onStreamFinished: {
        try { root.setupOutcome = JSON.parse(text).message || "Setup finished. Check again to inspect the result." }
        catch (e) { root.setupOutcome = "Setup did not return a result. Check ~/.cache/omarchy-agent-activity/install.log." }
      }
    }
    onExited: function(code) { root.inspectSetup(); if (code === 0) root.refresh() }
  }
  Process {
    id: reader
    command: ["python3", decodeURIComponent(Qt.resolvedUrl("bin/pilot_snapshot.py").toString().replace(/^file:\/\//, ""))]
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          var data = JSON.parse(text)
          if (data.version !== 1 || !Array.isArray(data.items)) throw new Error("Invalid snapshot")
          root.snapshot = data
          console.log("Agent Activity data source:", data.source || "Local LoongSuite Pilot output")
        } catch (e) { root.failure = "Could not read the local snapshot. Check Python and collector configuration." }
      }
    }
    onExited: function(code) { if (code !== 0) root.failure = "Reader failed. Check pilot.json and local file permissions." }
  }
  // Safety deadline only; it does not poll or spawn work while idle.
  Timer {
    interval: 5000
    running: reader.running
    onTriggered: { reader.running = false; root.failure = "Reading timed out. Try a smaller local dataset." }
  }
  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
      owner: root.hostWidget || root
    bar: root.bar
    open: root.opened
    focusTarget: keys
    contentWidth: panel.fittedContentWidth(Style.space(root.view === "activity" && browser.hasSession ? 1040 : 600))
    contentHeight: panel.fittedContentHeight(Style.space(root.view === "activity" && browser.hasSession ? 820 : 740))
    PanelKeyCatcher {
      id: keys
      anchors.fill: parent
      Shortcut {
        sequence: "Backspace"
        context: Qt.WindowShortcut
        enabled: root.opened && root.view === "activity" && browser.hasSession
        autoRepeat: false
        onActivated: browser.back()
      }
      onCloseRequested: { if (root.view !== "activity" || !browser.back()) root.close() }
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(t) {
        if (t === "r" || t === "R") root.refresh()
        else if (t === "a" || t === "A") { root.view = "activity"; scroller.contentY = 0 }
        else if (t === "o" || t === "O") { root.view = "overview"; scroller.contentY = 0 }
      }
      onMoveRequested: function(dx, dy) {
        if (root.view === "overview") {
          scroller.contentY = Math.max(0, Math.min(scroller.contentHeight - scroller.height, scroller.contentY + dy * Style.space(48)))
        } else if (root.view === "activity") {
          browser.move(dy)
          if (!browser.hasSession) scroller.contentY = Math.max(0, browser.y + browser.selectedPosition() - Style.space(100))
        }
      }
      onActivateRequested: { if (root.view === "activity") browser.activate() }
      Flickable {
        id: scroller
        anchors.fill: parent
        contentWidth: width
        contentHeight: body.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        Column {
          id: body
          width: parent.width
          spacing: Style.space(14)
          Row {
            width: parent.width
            spacing: Style.space(12)
            Text { text: "Agent Activity"; color: root.fg; font.family: root.family; font.pixelSize: Style.space(24); font.bold: true }
            Text {
              text: reader.running ? "Reading…" : "Refresh ↻"
              color: Commons.Color.accent
              font.family: root.family
              font.pixelSize: Style.space(13)
              anchors.verticalCenter: parent.verticalCenter
              MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: { root.refresh() } }
            }
            Text {
              text: "Setup"; color: Commons.Color.accent; font.family: root.family; font.pixelSize: Style.space(13)
              anchors.verticalCenter: parent.verticalCenter
              MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: { root.view = "setup"; scroller.contentY = 0; root.inspectSetup() } }
            }
          }
          Text {
            width: parent.width
            text: root.view === "setup" ? "Local collector setup · downloads only after review" : "Local agent sessions and usage\n" + (root.snapshot.contentEnabled ? "Content enabled for this dataset" : "Content hidden in this panel") + " · local file reader"
            color: root.secondary
            font.family: root.family
            font.pixelSize: Style.space(12)
            wrapMode: Text.Wrap
            textFormat: Text.PlainText
          }
          Text {
            visible: root.view !== "setup" && (root.failure !== "" || root.snapshot.status !== "ready")
            width: parent.width
            text: root.failure || root.snapshot.message || "No data yet."
            color: Commons.Color.urgent
            font.family: root.family
            font.pixelSize: Style.space(14)
            wrapMode: Text.Wrap
            textFormat: Text.PlainText
          }
          Row {
            width: parent.width; spacing: Style.space(8)
            Repeater {
              model: [{key: "overview", title: "Overview"}, {key: "activity", title: "Sessions"}]
              Rectangle {
                required property var modelData
                width: (body.width - Style.space(8)) / 2; height: Style.space(34); radius: Style.space(8)
                color: root.view === modelData.key ? Qt.rgba(Commons.Color.accent.r, Commons.Color.accent.g, Commons.Color.accent.b, 0.18) : "transparent"
                border.color: root.view === modelData.key ? Commons.Color.accent : root.secondary
                Text { anchors.centerIn: parent; text: modelData.title; color: root.fg; font.family: root.family; font.pixelSize: Style.space(13); font.bold: root.view === modelData.key }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: { root.view = modelData.key; scroller.contentY = 0 } }
              }
            }
          }
          Text {
            visible: root.view === "overview" && root.snapshot.status === "ready"
            width: parent.width; text: "Available local records · bounded scan · not account quota" + (root.snapshot.limited ? " · history truncated" : "")
            color: root.secondary; font.family: root.family; font.pixelSize: Style.space(11); wrapMode: Text.Wrap
          }
          UsageDashboard {
            visible: root.view === "overview" && root.snapshot.status === "ready"
            width: parent.width
            payload: root.snapshot.dashboard || ({ranges: {}, daily: [], heatmap: []})
            foreground: root.fg; accent: Commons.Color.accent; family: root.family; unit: Style.space(1)
          }
          SetupView {
            visible: root.view === "setup"
            width: parent.width
            plan: root.setupPlan; busy: setupApply.running || setupCheck.running; outcome: root.setupOutcome
            foreground: root.fg; accent: Commons.Color.accent; urgent: Commons.Color.urgent; family: root.family; unit: Style.space(1)
            onInspectRequested: root.inspectSetup()
            onApplyRequested: function(token) { if (!setupApply.running) { root.setupToken = token; root.setupOutcome = ""; setupApply.running = true } }
          }
          SessionBrowser {
            id: browser
            visible: root.view === "activity" && root.snapshot.status === "ready"
            width: parent.width
            sessions: root.snapshot.sessionList || []
            foreground: root.fg; accent: Commons.Color.accent; urgent: Commons.Color.urgent
            family: root.family; unit: Style.space(1)
            onNavigated: scroller.contentY = 0
          }
          Text {
            width: parent.width
            text: "Snapshot: " + root.when(root.snapshot.generatedAt) + "\nLatest event: " + root.when(root.snapshot.latestEvent) + "\n" + (root.snapshot.events || 0) + " events · " + (root.snapshot.filesRead || 0) + " files · " + (root.snapshot.elapsedMs || 0) + " ms" + (root.snapshot.limited ? " · window limited" : "") + ((root.snapshot.skippedLines || 0) ? " · " + root.snapshot.skippedLines + " skipped records" : "") + "\nO overview · A sessions · ↑↓ scroll/select · Enter inspect · R refresh · Backspace sessions · Esc back / close"
            color: root.secondary; font.family: root.family; font.pixelSize: Style.space(10); wrapMode: Text.Wrap
          }
        }
      }
    }
  }
}
