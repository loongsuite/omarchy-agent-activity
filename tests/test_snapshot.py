import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timedelta

spec = importlib.util.spec_from_file_location('snapshot', Path(__file__).parents[1] / 'bin/pilot_snapshot.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def event(id, name='tool.result', **extra):
    return {'event.id': id, 'event.name': name, 'time_unix_nano': 1792072100000000000,
            'gen_ai.agent.type': 'codex', 'gen_ai.session.id': 'session-a',
            'gen_ai.turn.id': 'turn-a', 'gen_ai.tool.call.id': 'call-a', **extra}


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, records, name='codex.jsonl'):
        p = self.root / name
        p.write_text(''.join(json.dumps(r) + '\n' for r in records))
        return p

    def test_duplicate_rotation_does_not_double_count(self):
        e = event('usage', 'llm.response', **{'gen_ai.usage.total_tokens': 70, 'gen_ai.usage.cache_read.input_tokens': 20})
        self.write([e]); self.write([e], 'rotated.jsonl')
        s = m.collect(self.root)
        self.assertEqual((s['events'], s['tokens'], s['sessions']), (1, 70, 1))

    def test_partial_append_recovered_after_completion(self):
        p = self.write([event('one')])
        with p.open('a') as f: f.write(json.dumps(event('two')))
        self.assertEqual(m.collect(self.root)['events'], 1)
        with p.open('a') as f: f.write('\n')
        self.assertEqual(m.collect(self.root)['events'], 2)

    def test_excluded_session_is_removed_from_views_and_usage_without_editing_logs(self):
        p = self.write([
            event('hidden-usage', 'llm.response', **{'gen_ai.usage.total_tokens': 70}),
            event('hidden-result', **{'error.type': 'Error'}),
            event('visible-usage', 'llm.response', **{'gen_ai.session.id': 'session-b', 'gen_ai.usage.total_tokens': 30}),
        ])
        original = p.read_bytes()
        s = m.collect(self.root, now=1792072100, excluded_session_ids=['session-a'])
        self.assertEqual((s['events'], s['sessions'], s['tokens'], s['errors']), (1, 1, 30, 0))
        self.assertEqual(s['items'], [])
        self.assertEqual([v['session'] for v in s['sessionList']], ['session-b'])
        self.assertEqual(s['dashboard']['ranges']['today']['tokens'], 30)
        self.assertEqual(p.read_bytes(), original)

    def test_truncation_is_fresh_scan(self):
        self.write([event('old')]); self.write([event('new')])
        self.assertEqual(m.collect(self.root)['items'][0]['id'], 'new')

    def test_content_is_opt_in(self):
        self.write([event('secret', **{'gen_ai.tool.call.result': 'secret-value', 'error.type': 'Error', 'error.message': 'secret-value'})])
        self.assertNotIn('secret-value', json.dumps(m.collect(self.root)))
        self.assertIn('secret-value', json.dumps(m.collect(self.root, True)))

    def test_calls_do_not_cross_sessions(self):
        self.write([event('call', 'tool.call', **{'gen_ai.tool.call.arguments': 'wrong command'}), event('result', **{'gen_ai.session.id': 'session-b'})])
        self.assertNotIn('wrong command', m.collect(self.root, True)['items'][0]['arguments'])

    def test_calls_do_not_cross_turns(self):
        self.write([event('call', 'tool.call', **{'gen_ai.tool.call.arguments': 'wrong command'}), event('result', **{'gen_ai.turn.id': 'turn-b'})])
        self.assertNotIn('wrong command', m.collect(self.root, True)['items'][0]['arguments'])

    def test_error_without_content_is_visible(self):
        self.write([event('one', **{'error.type': 'Timeout'})])
        s = m.collect(self.root)
        self.assertEqual(s['errors'], 1)
        self.assertEqual(s['items'][0]['status'], 'Source error')

    def test_codex_exec_wrapper_exit_is_only_hint(self):
        payload = [{'type': 'text', 'content': json.dumps({'chunk_id': 'abc', 'exit_code': 1, 'output': 'Assertion failed'})}]
        self.write([event('one', **{'gen_ai.tool.call.result': payload})])
        s = m.collect(self.root, True)
        self.assertEqual((s['errors'], s['review']), (0, 1))
        self.assertIn('Exit code: 1', s['items'][0]['output'])
        self.assertEqual(m.collect(self.root)['review'], 0)

    def test_arbitrary_error_text_is_not_failure(self):
        self.write([event('one', **{'gen_ai.tool.call.result': 'Examples of error: Process exited with code 1'})])
        s = m.collect(self.root, True)
        self.assertEqual((s['errors'], s['review']), (0, 0))

    def test_invalid_records_and_missing_output(self):
        self.write([[], {'message': 'raw log'}, event('one')])
        s = m.collect(self.root)
        self.assertEqual((s['skippedLines'], s['events']), (2, 1))
        self.assertEqual(m.collect(self.root / 'missing')['status'], 'unavailable')

    def test_symlink_is_not_followed(self):
        p = self.write([event('one')], 'outside.txt')
        (self.root / 'link.jsonl').symlink_to(p)
        self.assertEqual(m.collect(self.root)['events'], 0)

    def test_bounded_tail_and_skipped_partial_start(self):
        previous = m.PER_FILE
        m.PER_FILE = 512
        try:
            self.write([event('huge', **{'gen_ai.tool.call.result': 'x' * 1000}), event('last')])
            s = m.collect(self.root)
            self.assertTrue(s['limited'])
            self.assertLessEqual(s['bytesRead'], 512)
            self.assertEqual(s['items'][0]['id'], 'last')
        finally:
            m.PER_FILE = previous

    def test_dashboard_cache_and_reasoning_are_not_added_to_total(self):
        now = datetime(2026, 10, 19, 12).timestamp()
        e = event('usage', 'llm.response', **{'time_unix_nano': int(now*1e9),
                  'gen_ai.usage.input_tokens': 1000, 'gen_ai.usage.output_tokens': 100,
                  'gen_ai.usage.total_tokens': 1100, 'gen_ai.usage.cache_read.input_tokens': 800,
                  'gen_ai.usage.cache_creation.input_tokens': 0, 'gen_ai.usage.reasoning_output_tokens': 30,
                  'gen_ai.response.model': 'model-a'})
        self.write([e]); self.write([e], 'duplicate.jsonl')
        s = m.collect(self.root, now=now)['dashboard']['ranges']['today']
        self.assertEqual(s['tokens'], 1100)
        self.assertEqual(s['metrics']['cacheRate'], .8)
        self.assertEqual(s['metrics']['cacheWrite'], 0)
        self.assertEqual(s['metrics']['reasoning'], 30)
        self.assertEqual(s['models'], [{'name':'model-a', 'tokens':1100, 'share':1.0}])

    def test_dashboard_calendar_ranges_and_unknown_days(self):
        today = datetime(2026, 10, 19, 12)
        es = [event(str(i), 'llm.response', **{'time_unix_nano': int((today-timedelta(days=i)).timestamp()*1e9),
               'gen_ai.session.id':'s'+str(i), 'gen_ai.usage.total_tokens': 10}) for i in [0,1,6,7,29,30,90,-1]]
        self.write(es)
        d = m.collect(self.root, now=today.timestamp())['dashboard']
        self.assertEqual([d['ranges'][k]['tokens'] for k in ['today','week','month']], [10,30,50])
        self.assertEqual(d['ranges']['week']['sessions'],3)
        self.assertEqual(d['ranges']['month']['sessions'],5)
        self.assertEqual(len(d['heatmap']),182)
        self.assertEqual(d['daily'][-1]['tokens'],10)
        self.assertIsNone(d['daily'][-3]['tokens'])
        self.assertTrue(d['heatmap'][-1]['future'])

    def test_dashboard_missing_fields_are_unknown_and_partial_cache_has_no_ratio(self):
        now=datetime(2026,10,19,12).timestamp()
        self.write([event('a','llm.response', **{'time_unix_nano':int(now*1e9), 'gen_ai.usage.input_tokens':100,
                    'gen_ai.usage.output_tokens':10, 'gen_ai.usage.cache_read.input_tokens':80}),
                    event('b','llm.response', **{'time_unix_nano':int(now*1e9), 'gen_ai.usage.input_tokens':100,
                    'gen_ai.usage.output_tokens':10})])
        s=m.collect(self.root,now=now)['dashboard']['ranges']['today']
        self.assertEqual(s['tokens'],220)
        self.assertIsNone(s['metrics']['cacheRate'])
        self.assertIsNone(s['metrics']['reasoning'])
        self.assertIsNone(s['metrics']['cacheWrite'])
        self.assertEqual(s['fieldCounts']['cacheRead'],1)
        self.assertEqual(s['partialFields'],['cacheRead'])

    def test_dashboard_sessions_are_unique_per_client_and_models_partition_tokens(self):
        now=datetime(2026,10,19,12).timestamp()
        self.write([event(str(i),'llm.response', **{'time_unix_nano':int(now*1e9), 'gen_ai.agent.type':agent,
                    'gen_ai.response.model':model, 'gen_ai.usage.total_tokens':tokens})
                    for i,(agent,model,tokens) in enumerate([('codex','a',10),('codex','a',20),('claude','b',30)])])
        s=m.collect(self.root,now=now)['dashboard']['ranges']['today']
        self.assertEqual(s['sessions'],2)
        self.assertEqual([a['share'] for a in s['agents']],[.5,.5])
        self.assertEqual(sum(a['tokens'] for a in s['models']),s['tokens'])
        self.assertAlmostEqual(sum(a['share'] for a in s['models']),1)

    def test_session_turns_messages_and_privacy(self):
        prompt=[{'role':'user','parts':[{'type':'text','content':'<environment_context>private cwd</environment_context>\nFix checkout'}]}]
        self.write([event('start','other', **{'gen_ai.turn.start':True,'gen_ai.input.messages_delta':prompt}),
                    event('input','agent.input', **{'gen_ai.input.messages_delta':prompt}),
                    event('reply','llm.response', **{'gen_ai.usage.total_tokens':50,'gen_ai.output.messages':[
                        {'role':'assistant','parts':[{'type':'reasoning','content':'not-for-display'}, {'type':'text','content':'Checkout repaired'}]}]}),
                    event('next','agent.input', **{'gen_ai.turn.id':'turn-b','gen_ai.input.messages_delta':prompt}),
                    event('end','other', **{'gen_ai.turn.id':'turn-b','gen_ai.turn.end':True,'time_unix_nano':1792072190000000000})])
        s=m.collect(self.root,True)['sessionList'][0]
        self.assertEqual((s['title'],s['turns'],s['tokens'],s['durationSeconds']),('Fix checkout',2,50,90))
        self.assertEqual([r['kind'] for r in s['timeline']],['USER','ASSISTANT','USER'])
        self.assertNotIn('not-for-display',json.dumps(s))
        self.assertIsNone(s['cost'])
        private=json.dumps(m.collect(self.root,False)['sessionList'])
        self.assertNotIn('Fix checkout',private)
        self.assertNotIn('Checkout repaired',private)

    def test_session_unwraps_command_and_patch_with_real_exit_codes(self):
        patch='*** Begin Patch\n*** Update File: src/a.mjs\n-old\n+new\n*** End Patch'
        args='text(await tools.apply_patch('+json.dumps(patch)+'));text(await tools.exec_command({cmd:"npm test"}));'
        payload=[{'type':'text','content':'{}'},{'type':'text','content':json.dumps({'chunk_id':'c','exit_code':1,'output':'test failed','wall_time_seconds':.25})}]
        self.write([event('call','tool.call',**{'gen_ai.tool.call.arguments':args}),event('result',**{'gen_ai.tool.call.result':payload})])
        s=m.collect(self.root,True)['sessionList'][0]
        self.assertEqual(s['toolSteps'],2)
        self.assertEqual(s['failures'],1)
        self.assertEqual(s['timeline'][0]['title'],'Edit 1 file')
        self.assertEqual(s['timeline'][1]['title'],'npm test')
        self.assertEqual(s['timeline'][1]['durationMs'],250)
        self.assertEqual(s['timeline'][1]['output'],'test failed')

    def test_session_mismatched_wrapper_does_not_invent_operation_pairing(self):
        args='text(await tools.exec_command({cmd:"first"}));text(await tools.exec_command({cmd:"second"}));'
        payload=[{'type':'text','content':json.dumps({'chunk_id':'c','exit_code':1,'output':'failed'})}]
        self.write([event('call','tool.call',**{'gen_ai.tool.call.arguments':args}),event('result',**{'gen_ai.tool.call.result':payload})])
        s=m.collect(self.root,True)['sessionList'][0]
        self.assertEqual(len(s['timeline']),1)
        self.assertNotEqual(s['timeline'][0]['title'],'first')

    def test_session_cost_must_be_complete_and_pending_call_is_visible(self):
        self.write([event('a','llm.response',**{'gen_ai.usage.total_cost':.2}),event('b','llm.response'),event('c','tool.call')])
        s=m.collect(self.root,True)['sessionList'][0]
        self.assertIsNone(s['cost'])
        self.assertEqual(s['timeline'][-1]['status'],'Result not yet recorded')

    def test_session_detail_is_bounded_without_changing_summary(self):
        self.write([event(str(i),'llm.response',**{'gen_ai.usage.total_tokens':10}) for i in range(200)])
        s=m.collect(self.root,True)['sessionList'][0]
        self.assertEqual(s['tokens'],2000)
        self.assertEqual(len(s['timeline']),160)
        self.assertTrue(s['partial'])


if __name__ == '__main__':
    unittest.main()
