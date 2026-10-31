#!/usr/bin/env python3
import json, shutil, subprocess
from pathlib import Path

home = Path.home()
app = home/'.config/herdr-app'
binary = home/'.local/bin/herdr-app'
src = Path(__file__).resolve().parent
store = home/'.local/share/herdr-agent-history'
store.mkdir(parents=True, exist_ok=True)
shutil.copy2(src/'history.py', store/'history.py')
mod = app/'mods/agent-history'
mod.mkdir(parents=True, exist_ok=True)
shutil.copy2(src/'mod.json', mod/'mod.json')
(mod/'main.js').write_text((src/'main.js').read_text().replace('HISTORY_SCRIPT', str(store/'history.py')), encoding='utf-8')
status = json.loads(subprocess.check_output([str(binary), 'status'], text=True))
base = status.get('layout') or 'main'
if base == 'agent-history-layout':
    base = json.loads((app/'layouts/agent-history-layout.json').read_text()).get('_history_base', 'main')
layout = json.loads((app/'layouts'/f'{base}.json').read_text())
def find_tabs(node):
    if isinstance(node, dict):
        if node.get('id') == 'tabs': return node
        for v in node.values():
            found = find_tabs(v)
            if found: return found
    elif isinstance(node, list):
        for v in node:
            found = find_tabs(v)
            if found: return found
tabs = find_tabs(layout)
if not tabs or not tabs.get('content', {}).get('mod'): raise SystemExit('当前布局没有可用的标签栏，请先切换到 Herdr 主布局。')
original = tabs['content']['mod']
target = app/'mods/agent-history-tabs'
shutil.copytree(app/'mods'/original, target, dirs_exist_ok=True)
js = target/'main.js'
text = js.read_text()
needle = '      .child(button("tab-new",'
if needle not in text: raise SystemExit('标签栏结构已变化，无法安全安装。')
text = text.replace(needle, '      .child(button("agent-history", svg("mods/workspace-chrome/search.svg").size(15), () => run("mod.open", { name: "agent-history" })))\n'+needle, 1)
js.write_text(text)
tabs['content']['mod'] = 'agent-history-tabs'
layout['_history_base'] = base
(app/'layouts/agent-history-layout.json').write_text(json.dumps(layout, ensure_ascii=False, indent=2))
for p in (mod, target): subprocess.run([str(binary), 'check', str(p)], check=True)
subprocess.run([str(binary), 'do', 'layout.switch', json.dumps({'name':'agent-history-layout'})], check=True)
print('安装完成：点击窗口右上角的放大镜查看对话历史。')
