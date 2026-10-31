#!/usr/bin/env python3
import json, shutil, subprocess
from pathlib import Path

home = Path.home()
app = home/'.config/herdr-app'
binary = home/'.local/bin/herdr-app'
def layout_command(binary, command, payload):
    for attempt in range(3):
        result = subprocess.run([str(binary), 'do', command, json.dumps(payload)], capture_output=True, text=True)
        if result.returncode == 0: return
        if 'window did not answer' not in result.stdout + result.stderr: break
    raise RuntimeError(result.stdout + result.stderr)

src = Path(__file__).resolve().parent
store = home/'.local/share/herdr-agent-history'
store.mkdir(parents=True, exist_ok=True)
shutil.copy2(src/'history.py', store/'history.py')
mod = app/'mods/agent-history'
mod.mkdir(parents=True, exist_ok=True)
shutil.copy2(src/'mod.json', mod/'mod.json')
shutil.copy2(src/'sidebar-right.svg', mod/'sidebar-right.svg')
codex_app = Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')
codex = shutil.which('codex') or (str(codex_app) if codex_app.exists() else 'codex')
claude = shutil.which('claude') or str(home/'.local/bin/claude')
source = (src/'main.js').read_text().replace('HISTORY_SCRIPT', str(store/'history.py'))
source = source.replace('CODEX_BIN', json.dumps(codex)).replace('CLAUDE_BIN', json.dumps(claude))
(mod/'main.js').write_text(source, encoding='utf-8')
def app_status():
    try:
        return json.loads(subprocess.check_output([str(binary), 'status'], text=True, stderr=subprocess.DEVNULL))
    except (subprocess.CalledProcessError, OSError, json.JSONDecodeError):
        subprocess.run(['open', '-a', 'Herdr'], check=False)
        import time
        for _ in range(40):
            time.sleep(0.5)
            try:
                return json.loads(subprocess.check_output([str(binary), 'status'], text=True, stderr=subprocess.DEVNULL))
            except (subprocess.CalledProcessError, OSError, json.JSONDecodeError):
                pass
        raise SystemExit('Herdr 没有启动，请先手动打开 Herdr 后再运行安装脚本。')

status = app_status()
base = status.get('layout') or 'main'
restore_motion = base == 'desktop-motion-layout'
if restore_motion:
    base = json.loads((app/'layouts/desktop-motion-layout.json').read_text())['_motion_base']
if base == 'agent-history-layout':
    base = json.loads((app/'layouts/agent-history-layout.json').read_text()).get('_history_base', 'main')
layout = json.loads((app/'layouts'/f'{base}.json').read_text())
def find_tabs(node, target_id="tabs"):
    if isinstance(node, dict):
        if node.get('id') == target_id: return node
        for v in node.values():
            found = find_tabs(v, target_id)
            if found: return found
    elif isinstance(node, list):
        for v in node:
            found = find_tabs(v, target_id)
            if found: return found
tabs = find_tabs(layout)
if not tabs or not tabs.get('content', {}).get('mod'): raise SystemExit('当前布局没有可用的标签栏，请先切换到 Herdr 主布局。')
original = tabs['content']['mod']
target = app/'mods/agent-history-tabs'
shutil.copytree(app/'mods'/original, target, dirs_exist_ok=True)
js = target/'main.js'
text = js.read_text()
needle = '      .when(w?.buttons,'
if needle not in text: raise SystemExit('标签栏结构已变化，无法安全安装。')
text = text.replace(needle, '      .child(div().id("agent-history").h(26).px(8).flex_none().flex().items_center().justify_center().rounded(6).text_color(t.dim).hover(s => s.bg(t.hover).text_color(t.foreground)).on_mouse_down("left", stop).on_click(() => { const panel = find(layout(), "panel"), body = find(layout(), "panel-body"); if (panel && !panel.hidden && body?.active === "history-sidebar") run("agent-history.dismiss"); else { run("layout.select", {stack:"panel-body", child:"history-sidebar"}); run("layout.show", {id:"panel"}); run("agent-history.reveal"); } }).child(svg("mods/agent-history/sidebar-right.svg").size(15)))\n'+needle, 1)
text = text.replace('const enabled = shared("workspace.panels") ?? ["files", "changes"];', 'const enabled = [...(shared("workspace.panels") ?? ["files", "changes"]), "history-sidebar"];')
js.write_text(text)
tabs['content']['mod'] = 'agent-history-tabs'
body = find_tabs(layout, 'panel-body')
if not body: raise SystemExit('当前布局缺少右侧面板容器。')
body['children'].append({'id': 'history-sidebar', 'type': 'block', 'content': {'mod': 'agent-history', 'props': {'sidebar': True}}})
body['active'] = 'history-sidebar'
find_tabs(layout, 'panel')['hidden'] = False
layout['_history_base'] = base
(app/'layouts/agent-history-layout.json').write_text(json.dumps(layout, ensure_ascii=False, indent=2))
for p in (mod, target): subprocess.run([str(binary), 'check', str(p)], check=True)
layout_command(binary, 'layout.switch', {'name':'agent-history-layout'})
if restore_motion:
    import sys
    subprocess.run([sys.executable, str(src.parent/'desktop-motion/install.py')], check=True)
layout_command(binary, 'layout.show', {'id':'history-sidebar'})
print('安装完成：点击窗口右上角的侧边栏图标查看记录。')
