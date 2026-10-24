import QtQuick

Column {
  id: root
  property var payload: ({ranges: {}, daily: [], heatmap: []})
  property string rangeKey: "today"
  property color foreground: "#17283d"
  property color accent: "#3478f6"
  property string family: "sans-serif"
  property real unit: 1
  readonly property color secondary: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.76)
  readonly property var summary: (payload.ranges || {})[rangeKey] || ({metrics: {}, models: [], agents: []})
  readonly property var metrics: summary.metrics || ({})
  property string hoveredDay: "Hover a day to inspect recorded usage."
  spacing: 12 * unit
  function count(v) {
    if (v === null || v === undefined) return "—"
    if (v >= 1000000) return (v / 1000000).toFixed(2) + "M"
    if (v >= 1000) return (v / 1000).toFixed(1) + "K"
    return Math.round(v).toLocaleString()
  }
  function percent(v) { return v === null || v === undefined ? "—" : (v * 100).toFixed(1) + "%" }
  function seriesColor(i) { return [accent, "#1caa98", "#a878e6", "#edaa48", "#de6e9e"][i % 5] }
  component Label: Text {
    color: root.foreground
    font.family: root.family
    font.pixelSize: 13 * root.unit
    textFormat: Text.PlainText
    wrapMode: Text.Wrap
  }
  component Card: Rectangle {
    default property alias content: contents.data
    width: root.width
    implicitHeight: contents.implicitHeight + 32 * root.unit
    height: implicitHeight
    radius: 12 * root.unit
    color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.045)
    border.color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.12)
    Column {
      id: contents
      x: 16 * root.unit; y: 16 * root.unit
      width: parent.width - 32 * root.unit
      spacing: 12 * root.unit
    }
  }
  component Metric: Column {
    property string label: ""
    property string value: ""
    spacing: 5 * root.unit
    Label { width: parent.width; text: parent.label; color: root.secondary; font.pixelSize: 11 * root.unit }
    Label { width: parent.width; text: parent.value; color: root.accent; font.pixelSize: 21 * root.unit; font.bold: true }
  }
  Row {
    width: parent.width; spacing: 8 * root.unit
    Repeater {
      model: [{key:"today",title:"Today"},{key:"week",title:"7 days"},{key:"month",title:"30 days"}]
      Rectangle {
        required property var modelData
        width: (root.width - 16 * root.unit) / 3; height: 32 * root.unit; radius: 7 * root.unit
        color: root.rangeKey === modelData.key ? Qt.rgba(root.accent.r,root.accent.g,root.accent.b,0.18) : "transparent"
        border.color: root.rangeKey === modelData.key ? root.accent : Qt.rgba(root.foreground.r,root.foreground.g,root.foreground.b,0.15)
        Label { anchors.centerIn: parent; text: modelData.title; font.bold: root.rangeKey === modelData.key }
        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.rangeKey = modelData.key }
      }
    }
  }
  Card {
    Label { text: "RECORDED TOKEN USAGE"; color: root.secondary; font.pixelSize: 11 * root.unit; font.bold: true }
    Row {
      width: parent.width
      Label { width: parent.width * 0.62; text: root.count(root.summary.tokens); font.pixelSize: 42 * root.unit; font.bold: true }
      Column {
        width: parent.width * 0.38; spacing: 6 * root.unit
        Label { width: parent.width; text: (root.summary.sessions || 0) + " active sessions"; color: root.accent; font.bold: true }
        Label { width: parent.width; text: (root.summary.review || 0) + " results to review"; color: root.secondary }
      }
    }
    Row {
      width: parent.width; spacing: 12 * root.unit
      Metric { width: (parent.width - 24 * root.unit) / 3; label: "Model responses"; value: root.count(root.summary.usageEvents || 0) }
      Metric { width: (parent.width - 24 * root.unit) / 3; label: "Cache write"; value: root.count(root.metrics.cacheWrite) }
      Metric { width: (parent.width - 24 * root.unit) / 3; label: "Reasoning output"; value: root.count(root.metrics.reasoning) }
    }
  }
  Card {
    Label { text: "TOKEN COMPOSITION"; color: root.secondary; font.pixelSize: 11 * root.unit; font.bold: true }
    Row {
      width: parent.width; spacing: 12 * root.unit
      Metric { width: (parent.width - 24 * root.unit) / 3; label: "Input · includes cache"; value: root.count(root.metrics.input) }
      Metric { width: (parent.width - 24 * root.unit) / 3; label: "Output"; value: root.count(root.metrics.output) }
      Metric { width: (parent.width - 24 * root.unit) / 3; label: "Cache read / input"; value: root.percent(root.metrics.cacheRate) }
    }
    Label {
      width: parent.width; color: root.secondary; font.pixelSize: 10 * root.unit
      text: "Cache read: " + root.count(root.metrics.cacheRead) + ". Cache and reasoning are included in input/output, not added again. — means not reported." + ((root.summary.partialFields || []).length ? " Partial fields: " + root.summary.partialFields.join(", ") + "." : "")
    }
  }
  Card {
    Label { text: "DAILY TOKENS · LAST 7 DAYS"; color: root.secondary; font.pixelSize: 11 * root.unit; font.bold: true }
    Canvas {
      id: trend
      width: parent.width; height: 128 * root.unit
      property var points: root.payload.daily || []
      onPointsChanged: requestPaint()
      onWidthChanged: requestPaint()
      Connections { target: root; function onAccentChanged() { trend.requestPaint() } function onForegroundChanged() { trend.requestPaint() } }
      onPaint: {
        var ctx = getContext("2d"); ctx.reset()
        var max = 1
        for (var i = 0; i < points.length; i++) max = Math.max(max, points[i].tokens || 0)
        var left = 48 * root.unit, bottom = height - 26 * root.unit, plot = width - left
        ctx.font = (9 * root.unit) + "px " + root.family
        ctx.fillStyle = root.secondary
        ctx.fillText(root.count(max), 0, 12 * root.unit)
        ctx.fillText("0", 0, bottom)
        ctx.strokeStyle = Qt.rgba(root.foreground.r,root.foreground.g,root.foreground.b,0.16)
        for (var g=0;g<3;g++) { var yy=12*root.unit+(bottom-12*root.unit)*g/2; ctx.beginPath();ctx.moveTo(left,yy);ctx.lineTo(width,yy);ctx.stroke() }
        for (var j=0;j<points.length;j++) {
          var step=plot/7, x=left+j*step+step*.15, h=(bottom-12*root.unit)*(points[j].tokens || 0)/max
          ctx.fillStyle=root.accent
          if (points[j].tokens !== null) ctx.fillRect(x,bottom-Math.max(h,1),step*.7,Math.max(h,1))
          else {ctx.fillStyle=root.secondary;ctx.fillText("—",x+step*.15,bottom-5*root.unit)}
          ctx.fillStyle=root.secondary;ctx.fillText(points[j].label,x,bottom+19*root.unit)
        }
      }
    }
    Label { width: parent.width; text: "Empty days have no token records in the loaded data."; color: root.secondary; font.pixelSize: 10 * root.unit }
  }
  Card {
    Label { text: "CLIENTS · SHARE OF ACTIVE SESSIONS"; color: root.secondary; font.pixelSize: 11 * root.unit; font.bold: true }
    Row {
      width: parent.width; spacing: 16 * root.unit
      Item {
        width: 124 * root.unit; height: width
        Canvas {
          id: donut
          anchors.fill: parent
          property var groups: root.summary.agents || []
          onGroupsChanged: requestPaint()
          onWidthChanged: requestPaint()
          Connections { target: root; function onAccentChanged() { donut.requestPaint() } function onForegroundChanged() { donut.requestPaint() } }
          onPaint: {
            var ctx=getContext("2d");ctx.reset();var r=width*.4, cx=width/2, cy=height/2, a=-Math.PI/2
            ctx.lineWidth=width*.13
            ctx.strokeStyle=Qt.rgba(root.foreground.r,root.foreground.g,root.foreground.b,.12)
            ctx.beginPath();ctx.arc(cx,cy,r,0,Math.PI*2);ctx.stroke()
            for(var i=0;i<groups.length;i++){var end=a+groups[i].share*Math.PI*2;ctx.strokeStyle=root.seriesColor(i);ctx.beginPath();ctx.arc(cx,cy,r,a,end);ctx.stroke();a=end}
          }
        }
        Column {
          anchors.centerIn: parent; spacing: 2 * root.unit
          Label { anchors.horizontalCenter: parent.horizontalCenter; text: root.count(root.summary.sessions || 0); font.pixelSize: 26 * root.unit; font.bold: true }
          Label { anchors.horizontalCenter: parent.horizontalCenter; text: "sessions"; color: root.secondary; font.pixelSize: 10 * root.unit }
        }
      }
      Column {
        width: parent.width - 140 * root.unit; spacing: 10 * root.unit
        Repeater {
          model: root.summary.agents || []
          Row {
            required property var modelData
            required property int index
            width: parent.width; spacing: 8 * root.unit
            Rectangle { width: 5 * root.unit; height: 31 * root.unit; radius: 2; color: root.seriesColor(index) }
            Column {
              width: parent.width - 65 * root.unit
              Label { width: parent.width; text: modelData.name; font.bold: true; elide: Text.ElideRight; maximumLineCount: 1 }
              Label { text: modelData.sessions + " sessions"; color: root.secondary; font.pixelSize: 10 * root.unit }
            }
            Label { text: Math.round(modelData.share*100) + "%"; color: root.accent; font.bold: true }
          }
        }
        Label { visible: !(root.summary.agents || []).length; text: "No recorded sessions"; color: root.secondary }
      }
    }
  }
  Card {
    Label { text: "MODELS · SHARE OF REPORTED TOKENS"; color: root.secondary; font.pixelSize: 11 * root.unit; font.bold: true }
    Repeater {
      model: root.summary.models || []
      Column {
        required property var modelData
        required property int index
        width: parent.width; spacing: 6 * root.unit
        Row {
          width: parent.width
          Label { width: parent.width * .7; text: modelData.name; font.bold: true; elide: Text.ElideRight; maximumLineCount: 1 }
          Label { width: parent.width * .3; horizontalAlignment: Text.AlignRight; text: root.percent(modelData.share); color: root.accent }
        }
        Label { text: root.count(modelData.tokens) + " tokens"; color: root.secondary; font.pixelSize: 11 * root.unit }
        Rectangle {
          width: parent.width; height: 6 * root.unit; radius: height/2
          color: Qt.rgba(root.foreground.r,root.foreground.g,root.foreground.b,.1)
          Rectangle { width: parent.width * modelData.share; height: parent.height; radius: height/2; color: root.seriesColor(index) }
        }
      }
    }
    Label { visible: !(root.summary.models || []).length; text: "No reported token usage"; color: root.secondary }
  }
  Card {
    Label { text: "ACTIVITY · LAST 26 WEEKS"; color: root.secondary; font.pixelSize: 11 * root.unit; font.bold: true }
    Grid {
      width: parent.width; rows: 7; columns: 26; flow: Grid.TopToBottom; spacing: 3 * root.unit
      property real peak: {
        var peak=1, cells=root.payload.heatmap || []
        for(var i=0;i<cells.length;i++) peak=Math.max(peak,cells[i].tokens || 0)
        return peak
      }
      Repeater {
        model: root.payload.heatmap || []
        Rectangle {
          required property var modelData
          width: (parent.width-25*3*root.unit)/26; height: width; radius: 2 * root.unit
          color: modelData.tokens === null ? Qt.rgba(root.foreground.r,root.foreground.g,root.foreground.b,.07) : Qt.rgba(root.accent.r,root.accent.g,root.accent.b,.2+.8*Math.sqrt((modelData.tokens || 0)/parent.peak))
          opacity: modelData.future ? .25 : 1
          MouseArea {
            anchors.fill: parent; hoverEnabled: true
            onEntered: root.hoveredDay = modelData.date + " · " + (modelData.future ? "Future date" : modelData.tokens === null ? "No token records loaded" : modelData.tokens.toLocaleString() + " tokens")
          }
        }
      }
    }
    Label { width: parent.width; text: root.hoveredDay; color: root.secondary; font.pixelSize: 10 * root.unit }
    Label { width: parent.width; text: "Monday → Sunday in each column · intensity follows recorded tokens.\nAvailable records from " + (root.payload.earliest || "—") + " · " + (root.payload.timezone || "local time") + ". Empty cells do not prove inactivity."; color: root.secondary; font.pixelSize: 10 * root.unit }
  }
}
