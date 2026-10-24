#!/usr/bin/env python3
"""Bounded, read-only projection of Pilot JSONL. No network, database or daemon."""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import time
from datetime import datetime, timedelta

MAX_FILES = 24
MAX_BYTES = 16 * 1024 * 1024
PER_FILE = 4 * 1024 * 1024
MAX_EVENTS = 20000


def dashboard(events, rows, now):
    """Calendar-local summaries of the records actually read, never account quota."""
    today = datetime.fromtimestamp(now).date()
    start = today - timedelta(days=today.weekday() + 25 * 7)
    usage_fields = {'input': 'input_tokens', 'output': 'output_tokens',
                    'cacheRead': 'cache_read.input_tokens', 'cacheWrite': 'cache_creation.input_tokens',
                    'reasoning': 'reasoning_output_tokens'}
    dated = [(datetime.fromtimestamp(stamp(e)).date(), e) for e in events if stamp(e)]
    def summarize(first):
        selected = [e for day, e in dated if first <= day <= today]
        responses = [e for e in selected if e.get('event.name') == 'llm.response']
        sums = {k: 0 for k in usage_fields}
        known = {k: 0 for k in usage_fields}
        models = {}
        agents = {}
        sessions = set()
        total = 0
        reported = 0
        for e in selected:
            agent = text(e.get('gen_ai.agent.type')) or 'unknown'
            sid = text(e.get('gen_ai.session.id'))
            if sid:
                sessions.add((agent, sid))
                agents.setdefault(agent, set()).add(sid)
        for e in responses:
            for key, field in usage_fields.items():
                v = e.get('gen_ai.usage.' + field)
                if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v < 1e15:
                    sums[key] += v
                    known[key] += 1
            value = e.get('gen_ai.usage.total_tokens')
            if value is None and any('gen_ai.usage.' + k in e for k in ('input_tokens', 'output_tokens')):
                value = number(e.get('gen_ai.usage.input_tokens')) + number(e.get('gen_ai.usage.output_tokens'))
            if value is not None:
                value = number(value)
                total += value
                reported += 1
                model = text(e.get('gen_ai.response.model') or e.get('gen_ai.request.model')) or 'Unknown model'
                models[model] = models.get(model, 0) + value
        metrics = {k: sums[k] if known[k] else None for k in sums}
        # A ratio is only meaningful when both fields are present for every response.
        complete_cache = bool(responses) and known['cacheRead'] == known['input'] == len(responses)
        metrics['cacheRate'] = sums['cacheRead'] / sums['input'] if complete_cache and sums['input'] > 0 and sums['cacheRead'] <= sums['input'] else None
        relevant_rows = [r for r in rows if r['when'] and first <= datetime.fromtimestamp(r['when']).date() <= today]
        return dict(tokens=total if reported else None, sessions=len(sessions), usageEvents=len(responses),
                    metrics=metrics, fieldCounts=known,
                    partialFields=[k for k in known if 0 < known[k] < len(responses)],
                    review=sum(r['attention'] for r in relevant_rows),
                    models=[dict(name=k, tokens=v, share=v/total if total else 0) for k,v in sorted(models.items(), key=lambda kv: -kv[1])],
                    agents=[dict(name=k, sessions=len(v), share=len(v)/len(sessions) if sessions else 0) for k,v in sorted(agents.items(), key=lambda kv: -len(kv[1]))])
    buckets = {}
    observed = set()
    for day, e in dated:
        observed.add(day)
        if e.get('event.name') == 'llm.response':
            value = e.get('gen_ai.usage.total_tokens')
            if value is None and any('gen_ai.usage.' + k in e for k in ('input_tokens', 'output_tokens')):
                value = number(e.get('gen_ai.usage.input_tokens')) + number(e.get('gen_ai.usage.output_tokens'))
            if value is not None:
                buckets[day] = buckets.get(day, 0) + number(value)
    def day_record(day):
        return dict(date=day.isoformat(), label=day.strftime('%m-%d'), tokens=buckets.get(day),
                    observed=day in observed, future=day > today)
    return dict(today=today.isoformat(), timezone=time.tzname[time.localtime(now).tm_isdst],
                earliest=min(observed).isoformat() if observed else None,
                ranges={'today':summarize(today), 'week':summarize(today-timedelta(days=6)), 'month':summarize(today-timedelta(days=29))},
                daily=[day_record(today-timedelta(days=6-i)) for i in range(7)],
                heatmap=[day_record(start+timedelta(days=i)) for i in range(182)])


def text(value, limit=160):
    return str(value or '')[:limit]


def stamp(event):
    try:
        value = int(event.get('time_unix_nano', 0)) / 1e9
        return value if 0 < value < 32503680000 else 0
    except (ValueError, TypeError, OverflowError):
        return 0


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value < 1e15 else 0


def preview(value):
    if value is None:
        return 'Not captured by the source.'
    value = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return value[:2400] + ('\n[truncated]' if len(value) > 2400 else '')


def codex_exit_hint(payload):
    """Read a recognizable command envelope; never infer normalized success."""
    parts = payload if isinstance(payload, list) else [payload]
    for part in parts:
        value = part.get('content') if isinstance(part, dict) and part.get('type') == 'text' else part
        if not isinstance(value, str):
            continue
        try:
            obj = json.loads(value)
            if isinstance(obj, dict) and 'chunk_id' in obj and isinstance(obj.get('output'), str):
                code = obj.get('exit_code')
                if isinstance(code, int) and not isinstance(code, bool) and code != 0:
                    return code
        except (ValueError, RecursionError):
            pass
        match = re.search(r'^Chunk ID: [^\n]+\nWall time: [^\n]+\nProcess exited with code (\d+)\s*$', value, re.M)
        if match and int(match.group(1)) != 0:
            return int(match.group(1))
    return None


def tool_preview(payload):
    if not isinstance(payload, list):
        return preview(payload)
    parts = []
    for part in payload:
        if isinstance(part, dict) and part.get('type') == 'text':
            value = part.get('content', '')
            try:
                obj = json.loads(value)
                if isinstance(obj, dict) and 'chunk_id' in obj and isinstance(obj.get('output'), str):
                    value = 'Exit code: ' + str(obj.get('exit_code', 'unknown')) + '\n' + obj['output']
            except (ValueError, TypeError, RecursionError):
                pass
            parts.append(str(value))
    return preview('\n'.join(parts)) if parts else preview(payload)


def message_text(messages, role):
    if not isinstance(messages, list):
        return []
    output = []
    for message in messages:
        if not isinstance(message, dict) or message.get('role') != role:
            continue
        # Only visible text; never surface reasoning or system/developer context.
        parts = message.get('parts', [])
        if not isinstance(parts, list):
            continue
        value = '\n'.join(str(p.get('content', '')) for p in parts
                          if isinstance(p, dict) and p.get('type') == 'text')
        if role == 'user':
            value = re.sub(r'^\s*<environment_context>.*?</environment_context>\s*', '', value, flags=re.S)
        if value.strip():
            output.append(value.strip())
    return output


def clipped(value, limit=4000):
    value = str(value or '')
    return value[:limit] + ('\n[Display truncated]' if len(value) > limit else '')


def decoded_operations(arguments):
    """Recognize literal tool wrappers without evaluating any source code."""
    if not isinstance(arguments, str) or len(arguments) > 200000:
        return []
    starts = list(re.finditer(r'tools\.(exec_command|apply_patch)\(\s*', arguments))
    operations = []
    for i, match in enumerate(starts):
        value = arguments[match.end():starts[i+1].start() if i+1 < len(starts) else len(arguments)]
        if match.group(1) == 'exec_command':
            command = re.search(r'\bcmd\s*:\s*("(?:\\.|[^"\\])*")', value)
            if not command:
                return []
            literal = command.group(1)
        else:
            literal = value
        try:
            decoded, _ = json.JSONDecoder().raw_decode(literal)
        except (ValueError, RecursionError):
            return []
        if not isinstance(decoded, str):
            return []
        operations.append((match.group(1), decoded))
    return operations


def session_views(events, allow_content, limited):
    grouped = {}
    for e in events:
        sid = text(e.get('gen_ai.session.id'))
        if not sid:
            continue
        key = (text(e.get('gen_ai.agent.type')) or 'unknown', sid)
        grouped.setdefault(key, []).append(e)
    ordered_groups = sorted(grouped.items(), key=lambda kv: max(stamp(e) for e in kv[1]), reverse=True)
    sessions = []
    remaining_rows = 600
    for (agent, sid), es in ordered_groups[:30]:
        turns = list(dict.fromkeys(text(e.get('gen_ai.turn.id')) for e in es if e.get('gen_ai.turn.id')))
        turn_numbers = {turn:i+1 for i,turn in enumerate(turns)}
        times = [stamp(e) for e in es if stamp(e)]
        responses = [e for e in es if e.get('event.name') == 'llm.response']
        usages = [e for e in responses if any('gen_ai.usage.'+k in e for k in ('total_tokens','input_tokens','output_tokens'))]
        total = sum(number(e.get('gen_ai.usage.total_tokens')) if e.get('gen_ai.usage.total_tokens') is not None
                    else number(e.get('gen_ai.usage.input_tokens'))+number(e.get('gen_ai.usage.output_tokens')) for e in usages)
        cost_values = [e.get('gen_ai.usage.total_cost') for e in responses]
        valid_costs = [v for v in cost_values if isinstance(v,(int,float)) and not isinstance(v,bool) and 0 <= v < 1e15]
        cost = sum(valid_costs) if responses and len(valid_costs) == len(responses) else None
        timeline = []
        calls = {(text(e.get('gen_ai.turn.id')),text(e.get('gen_ai.tool.call.id'))):e for e in es if e.get('event.name')=='tool.call'}
        result_keys = {(text(e.get('gen_ai.turn.id')),text(e.get('gen_ai.tool.call.id'))) for e in es if e.get('event.name')=='tool.result'}
        seen_messages = set()
        user_title = ''
        def add(e, kind, title, content='', output='', status='', duration=None, tokens=None, suffix=''):
            timeline.append(dict(id=text(e['event.id'])+suffix, kind=kind, title=clipped(title,160),
                                 turn=turn_numbers.get(text(e.get('gen_ai.turn.id')),0), when=stamp(e),
                                 content=clipped(content) if allow_content else 'Content hidden.',
                                 output=clipped(output) if allow_content else 'Content hidden.',
                                 status=status, attention=status.startswith('Failed') or status=='Source error',
                                 durationMs=duration, tokens=tokens, traceId=text(e.get('trace_id'))))
        for e in es:
            name=e.get('event.name')
            if name=='tool.call' and (text(e.get('gen_ai.turn.id')),text(e.get('gen_ai.tool.call.id'))) not in result_keys:
                ops=decoded_operations(e.get('gen_ai.tool.call.arguments')) if allow_content else []
                label=ops[0][1].splitlines()[0] if len(ops)==1 and ops[0][0]=='exec_command' else (text(e.get('gen_ai.tool.name')) or 'Tool')+' invocation'
                add(e,'TOOL',label,preview(e.get('gen_ai.tool.call.arguments')) if allow_content else '',status='Result not yet recorded')
            # agent.input and turn-start duplicate a message; requests can contain earlier context.
            if allow_content and (name=='agent.input' or e.get('gen_ai.turn.start') or name=='llm.request'):
                for content in message_text(e.get('gen_ai.input.messages_delta', e.get('gen_ai.input.messages')), 'user'):
                    key=(text(e.get('gen_ai.turn.id')), content)
                    if key in seen_messages:
                        continue
                    seen_messages.add(key)
                    if not user_title:
                        user_title=content.splitlines()[0].split('. ')[0].strip()
                    add(e,'USER',content.splitlines()[0],content,suffix='-user-'+str(len(seen_messages)))
            if name=='llm.response':
                visible = message_text(e.get('gen_ai.output.messages'),'assistant') if allow_content else []
                model=text(e.get('gen_ai.response.model') or e.get('gen_ai.request.model')) or 'Model'
                token = number(e.get('gen_ai.usage.total_tokens')) if e.get('gen_ai.usage.total_tokens') is not None else (number(e.get('gen_ai.usage.input_tokens'))+number(e.get('gen_ai.usage.output_tokens')) if e in usages else None)
                if visible:
                    add(e,'ASSISTANT',visible[0].splitlines()[0], '\n\n'.join(visible),status='Reply',tokens=token)
                else:
                    finish=e.get('gen_ai.response.finish_reasons') or []
                    add(e,'MODEL',model + (' · requested tools' if 'tool_call' in finish else ' · response'),
                        'Model: '+model+'\nVisible reply text was not provided in this record.',status='Model response',tokens=token)
            if name=='tool.result':
                call=calls.get((text(e.get('gen_ai.turn.id')),text(e.get('gen_ai.tool.call.id'))),{})
                args=call.get('gen_ai.tool.call.arguments')
                payload=e.get('gen_ai.tool.call.result')
                operations=decoded_operations(args) if allow_content else []
                envelopes=[]
                if allow_content and isinstance(payload,list):
                    for part in payload:
                        try:
                            v=json.loads(part.get('content','')) if isinstance(part,dict) else None
                        except (ValueError,TypeError,RecursionError):
                            continue
                        if isinstance(v,dict):envelopes.append(v)
                aligned=bool(operations) and len(operations)==len(envelopes) and all(
                    op[0]!='exec_command' or ('exit_code' in env and isinstance(env.get('output'),str))
                    for op,env in zip(operations,envelopes))
                if aligned:
                    for i,((kind,body),env) in enumerate(zip(operations,envelopes)):
                        if kind=='exec_command':
                            code=env.get('exit_code')
                            status=('Command completed · exit 0' if code==0 else 'Failed · exit '+str(code)) if isinstance(code,int) else 'Command result · exit unknown'
                            duration=number(env['wall_time_seconds'])*1000 if isinstance(env.get('wall_time_seconds'),(int,float)) else None
                            add(e,'TOOL',body.splitlines()[0],body,env.get('output',''),status,duration,suffix='-'+str(i))
                        else:
                            paths=re.findall(r'^\*\*\* (?:Update|Add|Delete) File: (.+)$',body,re.M)
                            label='Edit '+str(len(paths))+' file'+('s' if len(paths)!=1 else '') if paths else 'Apply code patch'
                            add(e,'TOOL',label,body,'\n'.join(paths) or 'Patch response recorded.','Patch response',suffix='-'+str(i))
                else:
                    name=text(e.get('gen_ai.tool.name') or call.get('gen_ai.tool.name')) or 'Tool'
                    hint=codex_exit_hint(payload) if allow_content and agent=='codex' else None
                    status='Source error' if e.get('error.type') else ('Failed · exit '+str(hint) if hint is not None else 'Tool response · outcome unknown')
                    add(e,'TOOL',name+' invocation',preview(args) if allow_content else '',tool_preview(payload) if allow_content else '',status,
                        number(e['gen_ai.tool.call.duration']) if 'gen_ai.tool.call.duration' in e else None)
        timeline.sort(key=lambda r:r['when'])
        # Whole-window summaries remain correct even when displayed detail is capped.
        failed=sum(r['attention'] for r in timeline)
        tool_steps=sum(r['kind']=='TOOL' for r in timeline)
        cap=min(160,remaining_rows)
        visible_rows=timeline[-cap:] if cap else []
        remaining_rows-=len(visible_rows)
        last_turn=turns[-1] if turns else ''
        ended=any(e.get('gen_ai.turn.end') and text(e.get('gen_ai.turn.id'))==last_turn for e in es)
        workspace=next((str(e['workspace.path']) for e in es if e.get('workspace.path')),'') if allow_content else ''
        sessions.append(dict(key=agent+'|'+sid,session=sid,agent=agent,
                             title=clipped(user_title,100) if user_title else agent.title()+' session · '+sid[:8],
                             workspace=workspace, startedAt=min(times) if times else 0, endedAt=max(times) if times else 0,
                             durationSeconds=max(times)-min(times) if len(times)>1 else None,
                             turns=len(turns),tokens=total if usages else None,cost=cost,costLabel='Source-reported units' if cost is not None else 'Not reported',
                             status='Last turn ended' if ended else 'Latest state unknown',
                             failures=failed,toolSteps=tool_steps,modelCalls=len(responses),
                             timeline=visible_rows, timelineTotal=len(timeline),partial=limited or len(visible_rows)<len(timeline)))
    return sessions


def collect(directory, allow_content=False, provenance='Local Pilot output', now=None, excluded_session_ids=None):
    began = time.perf_counter()
    result = dict(version=1, status='ready', generatedAt=time.time(), source=provenance,
                  contentEnabled=allow_content, events=0, sessions=0, tokens=0, usageEvents=0,
                  errors=0, review=0, latestEvent=0, bytesRead=0, filesRead=0,
                  skippedLines=0, limited=False, items=[], message='')
    root = Path(directory).expanduser()
    if not root.is_dir():
        return dict(result, status='unavailable', message='Pilot output directory is not available. Configure outputDir in pilot.json.')
    files = []
    # Refuse symlinks and bound directory enumeration as well as actual reads.
    with os.scandir(root) as entries:
        for i, ent in enumerate(entries):
            if i >= 4096:
                result['limited'] = True
                break
            if ent.name.endswith('.jsonl') and ent.is_file(follow_symlinks=False):
                files.append((ent.stat(follow_symlinks=False).st_mtime_ns, Path(ent.path)))
    files.sort(reverse=True)
    result['limited'] |= len(files) > MAX_FILES
    events = {}
    for _, path in files[:MAX_FILES]:
        budget = min(PER_FILE, MAX_BYTES - result['bytesRead'])
        if budget <= 0 or len(events) >= MAX_EVENTS:
            result['limited'] = True
            break
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode):
                    continue
                start = max(0, info.st_size - budget)
                stream.seek(start)
                data = stream.read(budget)
                result['bytesRead'] += len(data)
                result['filesRead'] += 1
                if start:
                    result['limited'] = True
                    data = data.partition(b'\n')[2]
                # Never interpret the unfinished append at EOF as a complete event.
                lines = data.split(b'\n')[:-1]
                for line in reversed(lines):
                    if len(events) >= MAX_EVENTS:
                        result['limited'] = True
                        break
                    try:
                        event = json.loads(line)
                        if not isinstance(event, dict) or not isinstance(event.get('event.id'), str):
                            raise ValueError('not an event')
                        events.setdefault(event['event.id'], event)
                    except (ValueError, UnicodeDecodeError, RecursionError):
                        result['skippedLines'] += 1
        except OSError:
            result['skippedLines'] += 1
    # Reads run newest-line first; restore file order for equal timestamps.
    excluded = set(excluded_session_ids or [])
    ordered = sorted((e for e in reversed(list(events.values()))
                      if e.get('gen_ai.session.id') not in excluded), key=stamp)
    calls = {}
    rows = []
    sessions = set()
    for event in ordered:
        agent = text(event.get('gen_ai.agent.type')) or 'unknown'
        session = text(event.get('gen_ai.session.id'))
        if session:
            sessions.add((agent, session))
        result['latestEvent'] = max(result['latestEvent'], stamp(event))
        name = event.get('event.name')
        if name == 'llm.response':
            total = event.get('gen_ai.usage.total_tokens')
            result['tokens'] += number(total) if total is not None else number(event.get('gen_ai.usage.input_tokens')) + number(event.get('gen_ai.usage.output_tokens'))
            if any(k in event for k in ('gen_ai.usage.total_tokens', 'gen_ai.usage.input_tokens', 'gen_ai.usage.output_tokens')):
                result['usageEvents'] += 1
        call_id = event.get('gen_ai.tool.call.id')
        key = (agent, session, text(event.get('gen_ai.turn.id')), text(call_id))
        if name == 'tool.call' and call_id:
            calls[key] = event
        elif name == 'tool.result':
            call = calls.get(key, {}) if call_id else {}
            error = bool(event.get('error.type'))
            payload = event.get('gen_ai.tool.call.result')
            # A completed Codex invocation is not proof that its command succeeded.
            # This hint is explicitly distinguished from a normalized source error.
            hint = None
            if allow_content and agent == 'codex':
                hint = codex_exit_hint(payload)
            result['errors'] += int(error)
            result['review'] += int(hint is not None and not error)
            status = 'Source error' if error else ('Review: exit ' + str(hint) if hint is not None else 'Result received')
            rows.append(dict(id=text(event.get('event.id')), agent=agent, session=session,
                             tool=text(event.get('gen_ai.tool.name')) or text(call.get('gen_ai.tool.name')) or 'tool',
                             provider=text(event.get('gen_ai.provider.name')) or 'unknown',
                             when=stamp(event), status=status, attention=error or hint is not None,
                             errorType=text(event.get('error.type')),
                             durationMs=number(event.get('gen_ai.tool.call.duration')),
                             traceId=text(event.get('trace_id')), callId=text(call_id),
                             basis='Normalized error.type' if error else ('Exit code parsed from Codex tool-result envelope; not a normalized error.' if hint is not None else 'A tool result exists; success is not inferred.'),
                             arguments=preview(call.get('gen_ai.tool.call.arguments')) if allow_content else 'Content hidden. Enable allowContent explicitly for a trusted local dataset.',
                             output=tool_preview(payload) if allow_content else 'Content hidden.',
                             errorMessage=preview(event.get('error.message')) if allow_content and error else ''))
    result.update(events=len(ordered), sessions=len(sessions), items=list(reversed(rows))[:30])
    result['dashboard'] = dashboard(ordered, rows, time.time() if now is None else now)
    result['sessionList'] = session_views(ordered, allow_content, result['limited'])
    if not ordered:
        result.update(status='empty', message='No complete Pilot events found. Run an agent with Pilot enabled, then refresh.')
    result['elapsedMs'] = round((time.perf_counter() - began) * 1000, 2)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default=str(Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'omarchy/pilot.json'))
    parser.add_argument('--output-dir')
    args = parser.parse_args()
    config = {}
    path = Path(args.config)
    if path.exists():
        if path.stat().st_size > 16384:
            raise ValueError('Configuration exceeds 16 KiB')
        config = json.loads(path.read_text())
        if not isinstance(config, dict):
            raise ValueError('Configuration must be an object')
    directory = args.output_dir or config.get('outputDir', str(Path.home() / '.loongsuite-pilot/logs/output'))
    excluded = config.get('excludedSessionIds', [])
    if not isinstance(excluded, list) or not all(isinstance(s, str) for s in excluded):
        raise ValueError('excludedSessionIds must be a list of session IDs')
    snapshot = collect(directory, config.get('allowContent') is True,
                       text(config.get('provenance', 'Local Pilot output')),
                       excluded_session_ids=excluded)
    print(json.dumps(snapshot, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps(dict(version=1, status='unavailable', items=[], message='Cannot read Pilot data (' + type(exc).__name__ + '). Check local configuration and permissions.')))
        raise SystemExit(1)
