#!/usr/bin/env python3
"""Read session metadata, caching parsed JSONL headers between scans."""
import fcntl
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

HOME = Path.home()
CACHE_DIR = HOME / '.local/share/herdr-agent-history'
CACHE = CACHE_DIR / 'history-cache.json'
ROOTS = [('Codex', HOME / '.codex/sessions'), ('Claude', HOME / '.claude/projects')]


def parse(path, kind, mtime):
    sid = cwd = title = ''
    try:
        with path.open(encoding='utf-8') as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if kind == 'Codex':
                    payload = obj.get('payload') or {}
                    if obj.get('type') == 'session_meta':
                        sid, cwd = payload.get('id', ''), payload.get('cwd', '')
                    if obj.get('type') == 'event_msg' and payload.get('type') == 'user_message' and not title:
                        title = payload.get('message', '')
                else:
                    sid = sid or obj.get('sessionId', '')
                    cwd = cwd or obj.get('cwd', '')
                    if obj.get('type') == 'user' and not title:
                        content = obj.get('message', {}).get('content', '')
                        if isinstance(content, str):
                            title = content
                        elif isinstance(content, list):
                            title = ' '.join(x.get('text', '') for x in content if isinstance(x, dict) and x.get('type') == 'text')
                if sid and cwd and title:
                    break
        if sid and cwd and isinstance(title, str) and title:
            return {'id': sid, 'cwd': cwd, 'title': ' '.join(title.split())[:180], 'agent': kind, 'time': mtime, 'path': str(path)}
    except (OSError, UnicodeError, AttributeError, TypeError):
        pass
    return None


def scan():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with (CACHE_DIR / 'history-cache.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            saved = json.loads(CACHE.read_text(encoding='utf-8'))
            old = saved.get('files', {}) if saved.get('version') == 1 else {}
        except (OSError, ValueError, AttributeError):
            old = {}
        files, result = {}, []
        db = HOME / '.codex/state_5.sqlite'
        if db.exists():
            try:
                with sqlite3.connect(f'file:{db}?mode=ro', uri=True) as con:
                    for sid, path, cwd, title, updated in con.execute("SELECT id, rollout_path, cwd, title, updated_at FROM threads WHERE archived = 0 AND source NOT LIKE '%subagent%' ORDER BY updated_at DESC"):
                        if Path(path).is_file() and Path(cwd).is_dir():
                            result.append({'id': sid, 'cwd': cwd, 'title': ' '.join((title or 'Codex 对话').split())[:180], 'agent': 'Codex', 'time': updated, 'path': path})
            except (sqlite3.Error, OSError):
                pass
        indexed = {r['id'] for r in result}
        for kind, root in ROOTS:
            if not root.exists():
                # A disconnected volume must not erase its cached entries.
                for name, entry in old.items():
                    if entry.get('agent') == kind:
                        files[name] = entry
                continue
            for path in root.rglob('*.jsonl'):
                if 'subagents' in path.parts:
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                name = str(path)
                signature = [stat.st_mtime_ns, stat.st_size]
                entry = old.get(name)
                if not entry or entry.get('signature') != signature:
                    row = parse(path, kind, stat.st_mtime)
                    entry = {'signature': signature, 'agent': kind, 'row': row}
                files[name] = entry
                row = entry.get('row')
                if row and row['id'] not in indexed:
                    result.append(row)
                    indexed.add(row['id'])
        result.sort(key=lambda x: x['time'], reverse=True)
        try:
            fd, name = tempfile.mkstemp(prefix='history-', suffix='.tmp', dir=CACHE_DIR)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump({'version': 1, 'files': files}, f, ensure_ascii=False)
                os.replace(name, CACHE)
            finally:
                if os.path.exists(name):
                    os.unlink(name)
        except OSError:
            pass
        print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    if len(sys.argv) > 2 and sys.argv[1] == 'delete':
        roots = [root.resolve() for _, root in ROOTS]
        for raw in sys.argv[2:]:
            p = Path(raw).expanduser().resolve()
            if p.is_file() and any(root in p.parents for root in roots):
                try:
                    p.unlink()
                except OSError:
                    pass
    scan()
