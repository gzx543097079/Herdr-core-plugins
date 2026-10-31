#!/usr/bin/env python3
import json, os, sys
from pathlib import Path

def scan():
    result = []
    for kind, root in [('Codex', Path.home()/'.codex/sessions'), ('Claude', Path.home()/'.claude/projects')]:
        if not root.exists(): continue
        for path in root.rglob('*.jsonl'):
            if 'subagents' in path.parts: continue
            try:
                sid = cwd = title = ''
                with path.open(encoding='utf-8') as f:
                    for line in f:
                        try: obj = json.loads(line)
                        except (ValueError, UnicodeError): continue
                        if kind == 'Codex':
                            payload = obj.get('payload', {})
                            if obj.get('type') == 'session_meta': sid, cwd = payload.get('id', ''), payload.get('cwd', '')
                            if obj.get('type') == 'event_msg' and payload.get('type') == 'user_message' and not title: title = payload.get('message', '')
                        else:
                            sid = sid or obj.get('sessionId', '')
                            cwd = cwd or obj.get('cwd', '')
                            if obj.get('type') == 'user' and not title:
                                content = obj.get('message', {}).get('content', '')
                                if isinstance(content, str): title = content
                                elif isinstance(content, list): title = ' '.join(x.get('text', '') for x in content if isinstance(x, dict) and x.get('type') == 'text')
                        if sid and cwd and title: break
                if sid and cwd and title:
                    result.append({'id': sid, 'cwd': cwd, 'title': ' '.join(title.split())[:180], 'agent': kind, 'time': path.stat().st_mtime})
            except (OSError, UnicodeError, AttributeError, TypeError): continue
    result.sort(key=lambda x: x['time'], reverse=True)
    print(json.dumps(result, ensure_ascii=False))

if __name__ == '__main__': scan()
