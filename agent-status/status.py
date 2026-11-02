#!/usr/bin/env python3
"""读取聚焦终端所在项目的最新 Claude 会话状态：模式、模型与上下文用量。

只读会话文件末尾一小段，不修改 Claude Code，也不向终端发送内容。
用法：status.py <cwd> [终端标题]
"""

import json
import os
import sys
from pathlib import Path

HOME = Path.home()
TAIL = 196608


def tail_objects(path):
    """从文件末尾读一小段，按行解析 JSON；跳过被截断的首行。"""
    try:
        with path.open('rb') as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            start = max(0, size - TAIL)
            f.seek(start)
            data = f.read()
    except OSError:
        return []
    lines = data.split(b'\n')
    if start:
        lines = lines[1:]
    out = []
    for raw in lines:
        try:
            out.append(json.loads(raw))
        except (ValueError, UnicodeError):
            continue
    return out


def title_of(rows):
    custom = ai = ''
    for obj in rows:
        kind = obj.get('type')
        if kind == 'custom-title':
            custom = obj.get('customTitle') or custom
        elif kind == 'ai-title':
            ai = obj.get('aiTitle') or ai
    return custom or ai


def state_of(rows):
    mode = perm = model = ''
    usage = None
    for obj in rows:
        kind = obj.get('type')
        if kind == 'permission-mode':
            perm = obj.get('permissionMode') or perm
        elif kind == 'mode':
            mode = obj.get('mode') or mode
        message = obj.get('message') or {}
        if message.get('usage'):
            usage = message['usage']
            model = message.get('model') or model
    return mode, perm, model, usage


def context_of(usage):
    if not usage:
        return 0
    return (usage.get('input_tokens') or 0) + (usage.get('cache_read_input_tokens') or 0) \
        + (usage.get('cache_creation_input_tokens') or 0)


def window_of(model, settings_model):
    for name in (settings_model, model):
        if '[1m]' in (name or '').lower():
            return 1000000
    return 200000


def settings_model():
    try:
        data = json.loads((HOME / '.claude' / 'settings.json').read_text(encoding='utf-8'))
        return data.get('model') or ''
    except (OSError, ValueError):
        return ''


LABELS = {'auto': '自动', 'default': '普通', 'acceptEdits': '编辑',
          'plan': '计划', 'bypassPermissions': '免确认'}


def main():
    cwd = sys.argv[1] if len(sys.argv) > 1 else ''
    wanted = (sys.argv[2] if len(sys.argv) > 2 else '').strip()
    encoded = cwd.replace('/', '-')
    roots = [HOME / '.claude' / 'projects' / encoded,
             HOME / '.claude' / 'projects' / encoded.replace('.', '-')]
    root = next((path for path in roots if path.is_dir()), roots[0])
    try:
        files = sorted((p for p in root.glob('*.jsonl') if p.is_file()),
                       key=lambda p: p.stat().st_mtime, reverse=True)[:4]
    except OSError:
        files = []
    fallback = None
    for path in files:
        rows = tail_objects(path)
        title = title_of(rows)
        mode, perm, model, usage = state_of(rows)
        entry = {'mode': perm or mode, 'mode_label': LABELS.get(perm or mode, perm or mode or '普通'),
                 'model': model, 'context': context_of(usage),
                 'window': window_of(model, settings_model()),
                 'title': title, 'session': path.stem}
        if wanted and title == wanted:
            print(json.dumps(entry, ensure_ascii=False))
            return
        if fallback is None:
            fallback = entry
    print(json.dumps(fallback or {}, ensure_ascii=False))


if __name__ == '__main__':
    main()
