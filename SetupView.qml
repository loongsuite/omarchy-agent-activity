pragma ComponentBehavior: Bound
import QtQuick

Column {
  id: root
  property var plan: ({action: "none", observed: {}})
  property bool busy: false
  property string outcome: ""
  property color foreground: "white"
  property color accent: "lightblue"
  property color urgent: "salmon"
  property string family: "monospace"
  property real unit: 1
  property bool reviewed: false
  signal inspectRequested()
  signal applyRequested(string token)
  readonly property var observed: plan.observed || ({})
  readonly property color secondary: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.76)
  spacing: 14 * unit
  onPlanChanged: reviewed = false
  Text {
    width: parent.width
    text: "Collector setup"
    color: root.foreground; font.family: root.family; font.pixelSize: 20 * root.unit; font.bold: true
  }
  Text {
    width: parent.width
    text: root.observed.state === "missing" ? "Connect your local agent activity" : "Use your existing LoongSuite Pilot"
    color: root.foreground; font.family: root.family; font.pixelSize: 15 * root.unit; wrapMode: Text.Wrap
  }
  Rectangle {
    width: parent.width; height: facts.implicitHeight + 28 * root.unit
    radius: 8 * root.unit
    color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.05)
    Column {
      id: facts; anchors { left: parent.left; right: parent.right; top: parent.top; margins: 14 * root.unit }
      spacing: 8 * root.unit
      Repeater {
        model: [
          "Pilot: " + (root.observed.version || "Not detected") + " · " + (root.observed.service || "Checking"),
          "Content capture: " + (root.observed.capture || "Unknown"),
          "Backend configuration: " + (root.observed.remote || "Checking"),
          "Local output: " + (root.observed.outputDir || "Checking")
        ]
        Text { required property string modelData; width: facts.width; text: modelData; color: root.foreground; font.family: root.family; font.pixelSize: 12 * root.unit; wrapMode: Text.Wrap; textFormat: Text.PlainText }
      }
    }
  }
  Text {
    width: parent.width
    text: root.plan.message || "Inspecting the local setup…"
    color: root.plan.action === "none" ? root.urgent : root.foreground
    font.family: root.family; font.pixelSize: 13 * root.unit; wrapMode: Text.Wrap; textFormat: Text.PlainText
  }
  Text {
    width: parent.width
    text: root.plan.action === "install" ? "New installation · Pilot " + root.plan.version + "\nCodex only · conversation content off · local output only\nDownloads require internet. No Pilot source is bundled with this plugin."
      : "This panel does not change your collector’s capture or export settings. Hidden content in the panel does not mean content was not collected."
    color: root.secondary; font.family: root.family; font.pixelSize: 12 * root.unit; wrapMode: Text.Wrap
  }
  Column {
    visible: root.reviewed
    width: parent.width; spacing: 8 * root.unit
    Text { text: "Changes to apply"; color: root.foreground; font.family: root.family; font.pixelSize: 14 * root.unit; font.bold: true }
    Repeater {
      model: root.plan.effects || []
      Text { required property string modelData; width: root.width; text: "• " + modelData; color: root.secondary; font.family: root.family; font.pixelSize: 12 * root.unit; wrapMode: Text.Wrap; textFormat: Text.PlainText }
    }
  }
  Rectangle {
    objectName: "setupAction"
    visible: root.plan.action !== "none"
    width: parent.width; height: 42 * root.unit; radius: 8 * root.unit
    color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.18)
    border.color: root.accent
    opacity: root.busy ? 0.6 : 1
    Text {
      anchors.centerIn: parent
      text: root.busy ? "Working…" : !root.reviewed ? "Review setup" : root.plan.action === "connect" ? "Connect existing Pilot" : "Install & set up Pilot"
      color: root.foreground; font.family: root.family; font.pixelSize: 13 * root.unit
    }
    MouseArea {
      anchors.fill: parent; enabled: !root.busy; cursorShape: Qt.PointingHandCursor
      onClicked: { if (!root.reviewed) root.reviewed = true; else root.applyRequested(root.plan.token) }
    }
  }
  Text {
    width: parent.width
    visible: root.busy || root.outcome !== ""
    text: root.busy ? "Setup continues while this panel is closed. Do not restart the shell during installation.\nProgress: ~/.cache/omarchy-agent-activity/install.log" : root.outcome
    color: root.secondary; font.family: root.family; font.pixelSize: 12 * root.unit; wrapMode: Text.Wrap; textFormat: Text.PlainText
  }
  Text {
    text: "Check again ↻"; color: root.accent; font.family: root.family; font.pixelSize: 13 * root.unit
    MouseArea { anchors.fill: parent; enabled: !root.busy; cursorShape: Qt.PointingHandCursor; onClicked: root.inspectRequested() }
  }
  Text {
    width: parent.width
    text: "PoC · supports Pilot 1.13.0 + Codex. Upgrades and repairs remain manual. Existing configuration is preserved."
    color: root.secondary; font.family: root.family; font.pixelSize: 11 * root.unit; wrapMode: Text.Wrap
  }
}
