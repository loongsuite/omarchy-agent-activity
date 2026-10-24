import QtQuick
import QtTest
import "../.."

TestCase {
  id: suite
  name: "CollectorSetup"
  visible: true
  width: 700; height: 850; when: windowShown
  Component { id: factory; SetupView { width: 600; foreground: "#eeeeee"; accent: "#aabbff" } }
  Component {
    id: captureFactory
    Rectangle {
      width: 640; height: preview.implicitHeight + 40; color: "#1c1e2a"
      property alias view: preview
      SetupView { id: preview; x: 20; y: 20; width: 600; foreground: "#eeeeee"; accent: "#aabbff" }
    }
  }
  SignalSpy { id: applied; signalName: "applyRequested" }
  function test_review_before_apply() {
    var v = createTemporaryObject(factory, suite)
    verify(v !== null)
    v.plan = {action: "install", version: "1.13.0", token: "reviewed-plan", observed: {state:"missing"}, effects:["Local usage only"]}
    applied.target = v; applied.clear()
    var b = findChild(v, "setupAction")
    wait(50); mouseClick(b, b.width / 2, b.height / 2); compare(v.reviewed, true); compare(applied.count, 0)
    wait(50); mouseClick(b, b.width / 2, b.height / 2); compare(applied.count, 1); compare(applied.signalArguments[0][0], "reviewed-plan")
  }
  function test_plan_change_revokes_review_and_busy_blocks_action() {
    var v = createTemporaryObject(factory, suite)
    v.plan = {action:"connect", token:"a", observed:{state:"existing"}}
    applied.target = v; applied.clear()
    var b = findChild(v, "setupAction")
    wait(50); mouseClick(b, b.width / 2, b.height / 2); compare(v.reviewed,true)
    v.plan = {action:"connect", token:"b", observed:{state:"existing"}}
    compare(v.reviewed,false)
    v.busy=true; mouseClick(b); compare(v.reviewed,false); compare(applied.count,0)
  }
  function test_missing_and_existing_screenshots() {
    var capture = createTemporaryObject(captureFactory, suite)
    var v = capture.view
    v.plan = {action:"install",version:"1.13.0",message:"Install the official release with local usage-only defaults.",observed:{state:"missing",service:"not installed",capture:"unknown",outputDir:"~/.loongsuite-pilot/logs/output"},effects:["Download official Pilot", "Content off before first start", "Codex only; local output"]}
    v.reviewed=true; wait(50)
    verify(v.implicitHeight > 350)
    grabImage(capture).save("/tmp/agent-activity-setup-missing.png")
    v.plan={action:"connect",version:"1.13.0",message:"Reuse existing collector; preserve configuration.",observed:{state:"existing",version:"1.13.0",service:"running",capture:"on or unspecified",remote:"none configured in this file",outputDir:"~/.loongsuite-pilot/logs/output"},effects:["Connect panel to existing output"]}
    wait(50); grabImage(capture).save("/tmp/agent-activity-setup-existing.png")
  }
}
