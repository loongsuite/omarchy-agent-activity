import QtQuick

Column {
  id: root
  property var sessions: []
  property var currentSession: null
  property var currentStep: null
  property int sessionIndex: 0
  property int stepIndex: 0
  property color foreground: "#17283d"
  property color accent: "#3478f6"
  property color urgent: "#e36d79"
  property string family: "sans-serif"
  property real unit: 1
  readonly property color secondary: Qt.rgba(foreground.r,foreground.g,foreground.b,.76)
  readonly property bool hasSession: currentSession !== null
  signal navigated()
  spacing: 12 * unit
  function count(n) { return n === null || n === undefined ? "—" : Number(n).toLocaleString() }
  function elapsed(n) {
    if(n===null || n===undefined) return "—"
    n=Math.round(n)
    return n>=3600 ? Math.floor(n/3600)+"h "+Math.floor(n%3600/60)+"m" : n>=60 ? Math.floor(n/60)+"m "+n%60+"s" : n+"s"
  }
  function when(n) { return n ? Qt.formatDateTime(new Date(n*1000),"MMM d HH:mm:ss") : "Unknown time" }
  function roleColor(row) { return row.attention ? urgent : row.kind==="USER" ? accent : row.kind==="TOOL" ? "#dca857" : "#a786d5" }
  function chooseSession(i) {
    if(i<0 || i>=sessions.length) return
    sessionIndex=i;currentSession=sessions[i];stepIndex=0
    currentStep=currentSession.timeline.length ? currentSession.timeline[0] : null
    timelineScroll.contentY=0;detailScroll.contentY=0;navigated()
  }
  function chooseStep(i) {
    if(!currentSession || i<0 || i>=currentSession.timeline.length) return
    stepIndex=i;currentStep=currentSession.timeline[i];detailScroll.contentY=0
    var row=steps.itemAt(i)
    if(row) {
      var top=row.y
      if(top<timelineScroll.contentY) timelineScroll.contentY=top
      else if(top+row.height>timelineScroll.contentY+timelineScroll.height) timelineScroll.contentY=top+row.height-timelineScroll.height
    }
  }
  function back() {
    if(!currentSession) return false
    currentSession=null;currentStep=null;navigated();return true
  }
  function move(dy) {
    if(hasSession) chooseStep(Math.max(0,Math.min(currentSession.timeline.length-1,stepIndex+dy)))
    else sessionIndex=Math.max(0,Math.min(sessions.length-1,sessionIndex+dy))
  }
  function activate() { if(!hasSession) chooseSession(sessionIndex) }
  function selectedPosition() { var row=sessionCards.itemAt(sessionIndex); return row ? row.mapToItem(root, 0, 0).y : 0 }
  onSessionsChanged: {
    var oldKey=currentSession ? currentSession.key : ""
    currentSession=null;currentStep=null;sessionIndex=0
    for(var i=0;i<sessions.length;i++) if(sessions[i].key===oldKey) { chooseSession(i);break }
  }
  component Label: Text {
    color: root.foreground; font.family: root.family; font.pixelSize: 13 * root.unit
    textFormat: Text.PlainText; wrapMode: Text.Wrap
  }
  component Metric: Column {
    property string label: ""
    property string value: ""
    spacing: 4 * root.unit
    Label { width: parent.width; text: parent.label; color: root.secondary; font.pixelSize: 10 * root.unit }
    Label { width: parent.width; text: parent.value; font.bold: true; font.pixelSize: 15 * root.unit }
  }
  Column {
    visible: !root.hasSession
    width: parent.width; spacing: 12 * root.unit
    Label { text: "Sessions"; font.pixelSize: 22 * root.unit; font.bold: true }
    Label { width: parent.width; text: "Select a conversation to follow its turns, commands and replies."; color: root.secondary }
    Column {
      width: parent.width; spacing: 10 * root.unit
      Repeater {
        id: sessionCards
        model: root.sessions
        Rectangle {
          required property var modelData
          required property int index
          width: parent.width; height: cardBody.implicitHeight+28*root.unit; radius: 10*root.unit
          color: Qt.rgba(root.foreground.r,root.foreground.g,root.foreground.b,cardMouse.containsMouse?.09:.04)
          border.color: index===root.sessionIndex ? root.accent : Qt.rgba(root.foreground.r,root.foreground.g,root.foreground.b,.16)
          Column {
            id: cardBody
            x:14*root.unit;y:14*root.unit;width:parent.width-28*root.unit;spacing:9*root.unit
            Label { width: parent.width; text: modelData.title; font.pixelSize: 16*root.unit; font.bold:true; maximumLineCount:2; elide:Text.ElideRight }
            Label { width: parent.width; text: modelData.agent+" · "+root.when(modelData.startedAt)+" · "+modelData.status; color:root.secondary; font.pixelSize:11*root.unit }
            Row {
              width:parent.width;spacing:8*root.unit
              Metric { width:(parent.width-24*root.unit)/4;label:"Elapsed · observed";value:root.elapsed(modelData.durationSeconds) }
              Metric { width:(parent.width-24*root.unit)/4;label:"Turns";value:root.count(modelData.turns) }
              Metric { width:(parent.width-24*root.unit)/4;label:"Tokens";value:root.count(modelData.tokens) }
              Metric { width:(parent.width-24*root.unit)/4;label:"Reported cost";value:modelData.cost===null ? "Not reported" : Number(modelData.cost).toFixed(4) }
            }
            Label { width:parent.width;text:modelData.toolSteps+" tool steps · "+modelData.modelCalls+" model calls"+(modelData.failures ? " · "+modelData.failures+" failed commands/results" : "")+(modelData.partial ? " · partial history" : "");color:modelData.failures ? root.urgent : root.secondary;font.pixelSize:11*root.unit }
          }
          MouseArea { id:cardMouse;anchors.fill:parent;hoverEnabled:true;cursorShape:Qt.PointingHandCursor;onClicked:root.chooseSession(index) }
        }
      }
    }
    Label { visible:!root.sessions.length; text:"No recorded sessions";color:root.secondary }
  }
  Column {
    visible:root.hasSession
    width:parent.width;spacing:12*root.unit
    Label {
      text:"← Sessions";color:root.accent;font.bold:true
      MouseArea { anchors.fill:parent;cursorShape:Qt.PointingHandCursor;onClicked:root.back() }
    }
    Label { width:parent.width;text:root.currentSession ? root.currentSession.title : "";font.pixelSize:20*root.unit;font.bold:true;maximumLineCount:2;elide:Text.ElideRight }
    Row {
      width:parent.width;spacing:12*root.unit
      Metric { width:(parent.width-36*root.unit)/4;label:"Elapsed · observed";value:root.currentSession ? root.elapsed(root.currentSession.durationSeconds) : "—" }
      Metric { width:(parent.width-36*root.unit)/4;label:"Turns / tool steps";value:root.currentSession ? root.currentSession.turns+" / "+root.currentSession.toolSteps : "—" }
      Metric { width:(parent.width-36*root.unit)/4;label:"Total tokens";value:root.currentSession ? root.count(root.currentSession.tokens) : "—" }
      Metric { width:(parent.width-36*root.unit)/4;label:"Reported cost";value:root.currentSession && root.currentSession.cost!==null ? Number(root.currentSession.cost).toFixed(4)+" source units" : "Not reported" }
    }
    Label {
      width:parent.width;color:root.secondary;font.pixelSize:10*root.unit
      text:"Elapsed includes pauses between recorded events. Costs are not estimated. "+(root.currentSession && root.currentSession.partial ? "Partial history shown. " : "")+"Select a step below to inspect it."
    }
    Flow {
      width:parent.width;spacing:4*root.unit
      Repeater {
        model:root.currentSession ? root.currentSession.timeline : []
        Rectangle {
          required property var modelData
          required property int index
          width:12*root.unit;height:15*root.unit;radius:3*root.unit
          color:root.roleColor(modelData);border.width:index===root.stepIndex ? 2 : 0;border.color:root.foreground
          MouseArea { anchors.fill:parent;cursorShape:Qt.PointingHandCursor;onClicked:root.chooseStep(index) }
        }
      }
    }
    Label { width:parent.width;text:"Blue: user · Purple: model / assistant · Amber: tool · Red: failure";font.pixelSize:10*root.unit;color:root.secondary }
    Row {
      width:parent.width;height:510*root.unit;spacing:12*root.unit
      Rectangle {
        width:(parent.width-12*root.unit)*.51;height:parent.height;radius:8*root.unit
        color:Qt.rgba(root.foreground.r,root.foreground.g,root.foreground.b,.035)
        border.color:Qt.rgba(root.foreground.r,root.foreground.g,root.foreground.b,.14)
        Flickable {
          id:timelineScroll
          anchors.fill:parent;anchors.margins:8*root.unit;clip:true
          contentWidth:width;contentHeight:timelineBody.implicitHeight;boundsBehavior:Flickable.StopAtBounds
          Column {
            id:timelineBody;width:parent.width;spacing:6*root.unit
            Repeater {
              id:steps
              model:root.currentSession ? root.currentSession.timeline : []
              Column {
                required property var modelData
                required property int index
                width:parent.width;spacing:5*root.unit
                Label {
                  visible:index===0 || modelData.turn!==root.currentSession.timeline[index-1].turn
                  width:parent.width;text:modelData.turn ? "TURN "+modelData.turn : "UNASSIGNED TURN"
                  color:root.secondary;font.bold:true;font.pixelSize:11*root.unit;topPadding:8*root.unit;bottomPadding:5*root.unit
                }
                Rectangle {
                  width:parent.width;height:rowBody.implicitHeight+20*root.unit;radius:6*root.unit
                  color:index===root.stepIndex ? Qt.rgba(root.accent.r,root.accent.g,root.accent.b,.14) : "transparent"
                  border.color:index===root.stepIndex ? root.accent : "transparent"
                  Column {
                    id:rowBody;x:10*root.unit;y:10*root.unit;width:parent.width-20*root.unit;spacing:5*root.unit
                    Label { text:modelData.kind+" · "+Qt.formatDateTime(new Date(modelData.when*1000),"HH:mm:ss");color:root.roleColor(modelData);font.pixelSize:10*root.unit;font.bold:true }
                    Label { width:parent.width;text:modelData.title;maximumLineCount:2;elide:Text.ElideRight;font.bold:modelData.kind==="USER" || modelData.kind==="ASSISTANT" }
                    Label { visible:modelData.status!=="";width:parent.width;text:modelData.status+(modelData.tokens!==null ? " · "+root.count(modelData.tokens)+" tokens" : "");color:modelData.attention ? root.urgent : root.secondary;font.pixelSize:10*root.unit }
                  }
                  MouseArea { anchors.fill:parent;cursorShape:Qt.PointingHandCursor;onClicked:root.chooseStep(index) }
                }
              }
            }
          }
        }
      }
      Rectangle {
        width:(parent.width-12*root.unit)*.49;height:parent.height;radius:8*root.unit
        color:Qt.rgba(root.foreground.r,root.foreground.g,root.foreground.b,.04)
        border.color:Qt.rgba(root.foreground.r,root.foreground.g,root.foreground.b,.14)
        Flickable {
          id:detailScroll
          anchors.fill:parent;anchors.margins:14*root.unit;clip:true
          contentWidth:width;contentHeight:detailBody.implicitHeight;boundsBehavior:Flickable.StopAtBounds
          Column {
            id:detailBody;width:parent.width;spacing:12*root.unit
            Label { text:root.currentStep ? root.currentStep.kind+" · TURN "+root.currentStep.turn : "Select a step";color:root.currentStep ? root.roleColor(root.currentStep) : root.secondary;font.bold:true }
            Label { width:parent.width;text:root.currentStep ? root.currentStep.title : "";font.pixelSize:16*root.unit;font.bold:true;wrapMode:Text.WrapAnywhere }
            Label { width:parent.width;text:root.currentStep ? root.currentStep.status+(root.currentStep.durationMs!==null ? " · "+Math.round(root.currentStep.durationMs)+" ms" : "") : "";color:root.currentStep && root.currentStep.attention ? root.urgent : root.secondary;font.pixelSize:11*root.unit }
            Label { text:root.currentStep && root.currentStep.kind==="TOOL" ? "COMMAND / CHANGE" : "MESSAGE";color:root.accent;font.pixelSize:10*root.unit;font.bold:true }
            Label { width:parent.width;text:root.currentStep ? root.currentStep.content : "";wrapMode:Text.WrapAnywhere;font.pixelSize:12*root.unit }
            Label { visible:root.currentStep && root.currentStep.output!=="";text:"RESULT";color:root.accent;font.pixelSize:10*root.unit;font.bold:true }
            Label { width:parent.width;visible:root.currentStep && root.currentStep.output!=="";text:root.currentStep ? root.currentStep.output : "";wrapMode:Text.WrapAnywhere;font.pixelSize:12*root.unit }
            Label { width:parent.width;text:root.currentStep ? root.when(root.currentStep.when)+"\nTrace: "+(root.currentStep.traceId || "Not reported") : "";color:root.secondary;font.pixelSize:10*root.unit;wrapMode:Text.WrapAnywhere }
          }
        }
      }
    }
    Label {
      width:parent.width;text:root.currentSession ? "Session: "+root.currentSession.session+"\n"+root.currentSession.workspace : ""
      color:root.secondary;font.pixelSize:10*root.unit;wrapMode:Text.WrapAnywhere
    }
  }
}
