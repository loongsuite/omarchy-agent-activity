import QtQuick
import QtTest
import "../.."
TestCase {
  id: suite
  name: "Sessions"
  width: 1100; height: 900; when: windowShown
  Component { id: factory; SessionBrowser { width: 1000 } }
  function sample() {
    return [{key:"codex|s",session:"s",agent:"codex",title:"Repair checkout",workspace:"/lab",startedAt:100,endedAt:190,durationSeconds:90,turns:2,tokens:1000,cost:null,costLabel:"Not reported",status:"Last turn ended",failures:1,toolSteps:1,modelCalls:1,partial:false,timeline:[
      {id:"1",kind:"USER",title:"Fix checkout",turn:1,when:100,content:"Fix checkout",output:"",status:"",attention:false,durationMs:null,tokens:null,traceId:"t"},
      {id:"2",kind:"TOOL",title:"npm test",turn:1,when:110,content:"npm test",output:"Failed assertion",status:"Failed · exit 1",attention:true,durationMs:100,tokens:null,traceId:"t"},
      {id:"3",kind:"ASSISTANT",title:"Fixed",turn:2,when:190,content:"Fixed",output:"",status:"Reply",attention:false,durationMs:null,tokens:1000,traceId:"t2"}
    ]}]
  }
  function test_drilldown_and_back() {
    var v=createTemporaryObject(factory,suite);verify(v!==null)
    v.sessions=sample();compare(v.hasSession,false)
    v.activate();compare(v.hasSession,true);compare(v.currentSession.turns,2)
    v.move(1);compare(v.currentStep.title,"npm test");compare(v.currentStep.output,"Failed assertion")
    v.chooseStep(2);compare(v.currentStep.kind,"ASSISTANT")
    verify(v.back());compare(v.hasSession,false);verify(!v.back())
  }
  function test_refresh_preserves_session_and_resize() {
    var v=createTemporaryObject(factory,suite);v.sessions=sample();v.chooseSession(0)
    v.sessions=sample();compare(v.currentSession.key,"codex|s")
    v.width=600;wait(50);verify(v.implicitHeight>500)
    compare(v.elapsed(90),"1m 30s");compare(v.elapsed(null),"—")
    v.sessions=[];compare(v.hasSession,false)
  }
}
