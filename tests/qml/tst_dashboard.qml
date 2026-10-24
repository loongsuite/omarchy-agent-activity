import QtQuick
import QtTest
import "../.."

TestCase {
  id: testCase
  name: "UsageDashboard"
  width: 650; height: 900
  when: windowShown
  Component { id: factory; UsageDashboard { width: 600 } }
  function test_missing_and_zero_values() {
    var view = createTemporaryObject(factory, testCase)
    verify(view !== null)
    compare(view.count(null), "—")
    compare(view.count(0), "0")
    compare(view.percent(null), "—")
    compare(view.percent(0.8), "80.0%")
    verify(view.implicitHeight > 500)
  }
  function test_live_range_binding() {
    var view = createTemporaryObject(factory, testCase)
    view.payload = {ranges: {today: {tokens:1100,sessions:1,metrics:{input:1000,output:100,cacheRate:.8},models:[{name:"model-a",tokens:1100,share:1}],agents:[{name:"codex",sessions:1,share:1}]},week:{tokens:2200,sessions:2,metrics:{},models:[],agents:[]}},daily:[],heatmap:[]}
    compare(view.summary.tokens, 1100)
    view.rangeKey = "week"
    compare(view.summary.tokens, 2200)
    view.width = 380
    wait(50)
    compare(view.width, 380)
    verify(view.implicitHeight > 500)
  }
}
