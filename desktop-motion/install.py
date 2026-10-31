#!/usr/bin/env python3
"""Clone the active desktop layout; patch only recognized native panel sources."""

# 独立运行时交给管理器组合布局；管理器调用时执行下方实际安装逻辑。
if __name__ == '__main__':
    import os
    import sys
    from pathlib import Path
    if os.environ.get('HERDR_PLUGIN_COMPOSE') != '1':
        if len(sys.argv) > 2 or (len(sys.argv) == 2 and sys.argv[1] != '--reduce-motion'):
            raise SystemExit('用法：install.py [--reduce-motion]')
        if '--reduce-motion' in sys.argv:
            os.environ['HERDR_MOTION_REDUCED'] = '1'
        manager = Path(__file__).resolve().parent.parent / 'plugin-manager/server.py'
        os.execv(sys.executable, [sys.executable, str(manager), '--action', 'motion', 'install'])

import argparse
import json
import shutil
import subprocess
from pathlib import Path

APP = Path.home()/'.config/herdr-app'
BIN = Path.home()/'.local/bin/herdr-app'

def layout_command(binary, command, payload):
    for attempt in range(3):
        result = subprocess.run([str(binary), 'do', command, json.dumps(payload)], capture_output=True, text=True)
        if result.returncode == 0: return
        if 'window did not answer' not in result.stdout + result.stderr: break
    raise RuntimeError(result.stdout + result.stderr)

def replace(source, old, new):
    if old not in source:
        raise RuntimeError('Herdr 模块结构已变化，停止安装：' + old[:90])
    return source.replace(old, new, 1)

def patch_tabs(s, duration):
    s = s.replace('setShared, ', '').replace('setShared("history.panel-motion", Date.now()); ', '')
    # Stable per-button identity: native GPUI interpolates opacity after selection.
    s = replace(s, '.text_size(12).bg(on ?', f'.opacity(on ? 1 : 0.78).transition("opacity", {duration}).text_size(12).bg(on ?')
    s = replace(s, '.border(1).border_color(c.active ?', f'.opacity(c.active ? 1 : 0.82).transition("opacity", {duration}).border(1).border_color(c.active ?')
    effect = '''.when(c.status === "working", el => el.child(div().absolute().bottom(0).left(4).right(4).h(4).rounded(2).overflow_hidden().bg(t.working + "55")
          .child(div().absolute().left(0).top(0).w(24).h(4).rounded(2).bg(t.working).loop("left", {from: -16, to: 70, period: 1500, easing: "linear"}))))'''
    if not duration:
        effect = '''.when(c.status === "working", el => el.child(div().absolute().bottom(0).left(4).right(4).h(3).rounded(2).bg(t.working)))'''
    s = replace(s, 'return h_flex().id(`tab-${c.id}`).h(29)', 'return h_flex().id(`tab-${c.id}`).relative().h(29)')
    s = replace(s, '        .when(Boolean(program?.icon),', '        ' + effect + '\n        .when(Boolean(program?.icon),')
    return s

def patch_files(s, duration):
    s = replace(s, 'Editor, EditorState }', 'Editor, EditorState, Scrollbar, v_virtual_list }')
    # Publish the directory before waiting for Git decoration.
    s = replace(s, '          await this.loadFolder(path, context);', '          await this.loadFolder(path, context);\n          if (path === "" && this.current(context)) cx.notify();')
    # Coalesce bursts from build output without dropping the final event.
    s = replace(s, 'if (this.current(context)) this.refresh(cx);', 'if (this.current(context)) this.scheduleRefresh(cx);')
    s = replace(s, '  current(context) {', '''  scheduleRefresh(cx) {
    if (this.refreshQueued) return;
    this.refreshQueued = true;
    cx.timer.after(180, cx => { this.refreshQueued = false; this.refresh(cx); });
  }

  current(context) {''')
    s = replace(s, 'if (!cwd || this.loading) return;', 'if (!cwd) return;\n    if (this.loading) { this.refreshAgain = true; return; }')
    s = replace(s, 'finally { if (this.context === context) this.loading = false; cx.notify(); }', 'finally { if (this.context === context) { this.loading = false; if (this.refreshAgain) { this.refreshAgain = false; this.scheduleRefresh(cx); } } cx.notify(); }')
    # Flatten cheap metadata; construct native row elements only for the viewport.
    start=s.index('      out.push(h_flex()')
    end=s.index('\n      if (entry.dir && open)', start)
    row=s[start:end].replace(".on_click((_e, cx) => this.pick(f.path, cx))", "").replace('      out.push(', '    return ', 1)
    assert row.endswith('));')
    row=row[:-2]+';'
    row=row.replace('.on_click((_e, cx) => entry.dir ? this.toggle(path, cx) : this.show(path, cx))', '')
    s=s[:start]+'      out.push({ entry, path, open, mark, depth });'+s[end:]
    s=replace(s, '  render(cx) {', '  fileRow({entry, path, open, mark, depth}, t) {\n'+row+'\n  }\n\n  render(cx) {')
    s=replace(s, '    const t = theme();\n    return v_flex()', '    const t = theme(), visible = this.rows("", 0, [], theme());\n    return v_flex()')
    s=replace(s, 'v_flex().id("files-tree").flex_1().min_h(0).overflow_y_scrollbar().p(6).children(this.rows("", 0, [], t))', '''v_flex().id("files-tree").flex_1().min_h(0).relative().p(6)
        .child(v_virtual_list("motion-files-rows", visible.length, 28, i => visible[i].path,
          range => visible.slice(range.start, range.end).map(row => this.fileRow(row, t))).size_full().on_item_click((path, cx) => { const row = visible.find(r => r.path === path); if (row) row.entry.dir ? this.toggle(path, cx) : this.show(path, cx); }))
        .child(Scrollbar.vertical("motion-files-rows").viewport_from_layout().absolute().inset_0())''')
    s=replace(s, '.id("files").size_full()', f'.id("files").opacity(this.loading ? 0.9 : 1).transition("opacity", {duration}).size_full()')
    return s

def patch_changes(s, duration):
    s=replace(s, 'if (this.watched === root) this.refresh(cx);', 'if (this.watched === root) this.scheduleRefresh(cx);')
    s=replace(s, '  refresh(cx) {', '''  scheduleRefresh(cx) {
    if (this.refreshQueued) return;
    this.refreshQueued = true;
    cx.timer.after(180, cx => { this.refreshQueued = false; this.refresh(cx); });
  }

  refresh(cx) {''')
    s=replace(s, 'if (this.loading || this.busy) return;', 'if (this.loading || this.busy) { this.refreshAgain = true; return; }')
    s=replace(s, 'const status = await git(["status", "--porcelain=v1", "-z", "--no-renames", "--untracked-files=all"]);', '''const [status, head] = await Promise.all([
          git(["status", "--porcelain=v1", "-z", "--no-renames", "--untracked-files=all"]),
          git(["rev-parse", "--verify", "HEAD"])
        ]);''')
    s=replace(s, '        const head = await git(["rev-parse", "--verify", "HEAD"]);', '')
    s=replace(s, '[await git(["diff", "--cached", "--numstat", "-z", "--no-renames"]), await git(["diff", "--numstat", "-z", "--no-renames"])]', 'await Promise.all([git(["diff", "--cached", "--numstat", "-z", "--no-renames"]), git(["diff", "--numstat", "-z", "--no-renames"])])')
    s=replace(s, '        this.watch(root, cx);', '        this.watch(root, cx);\n        cx.notify(); // Show the file list before fetching the selected diff.')
    s=replace(s, 'finally { this.loading = false; cx.notify(); }', 'finally { this.loading = false; if (this.refreshAgain) { this.refreshAgain = false; this.scheduleRefresh(cx); } cx.notify(); }')
    # Keep unchanged diff metadata rather than allocating it again on every refresh.
    s=replace(s, '    this.rows = diffRows(lines);', '    const signature = JSON.stringify(lines);\n    if (signature === this.linesSignature) return;\n    this.linesSignature = signature;\n    this.rows = diffRows(lines);')
    start=s.index('        const parts = f.path.split')
    end=s.index('\n      })).when(!this.files.length',start)
    row=s[start:end].replace(".on_click((_e, cx) => this.pick(f.path, cx))", "")
    s=s[:start]+s[end+1:]
    s=replace(s, '  render(cx) {', '  changeRow(f, t) {\n'+row+'\n  }\n\n  render(cx) {')
    s=replace(s, '.overflow_y_scrollbar().p(6).border_b(1).border_color(t.border).children(this.files.map((f) => {\n      }))', '''.relative().p(6).border_b(1).border_color(t.border)
        .child(v_virtual_list("motion-changes-rows", this.files.length, 28, i => this.files[i].path,
          range => this.files.slice(range.start, range.end).map(f => this.changeRow(f, t))).size_full().on_item_click((path, cx) => this.pick(path, cx)))
        .child(Scrollbar.vertical("motion-changes-rows").viewport_from_layout().absolute().inset_0())''')
    s=replace(s, '.id("changes").size_full()', f'.id("changes").opacity(this.loading ? 0.9 : 1).transition("opacity", {duration}).size_full()')
    return s

def nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values(): yield from nodes(child)
    elif isinstance(value, list):
        for child in value: yield from nodes(child)

def install(reduced=False):
    import time
    for attempt in range(3):
        result=subprocess.run([str(BIN),'status'],capture_output=True,text=True)
        if result.returncode == 0: break
        time.sleep(0.2)
    if result.returncode: raise RuntimeError(result.stdout + result.stderr)
    status=json.loads(result.stdout)
    base=status['layout']
    if base=='desktop-motion-layout':
        base=json.loads((APP/'layouts/desktop-motion-layout.json').read_text())['_motion_base']
    layout=json.loads((APP/'layouts'/f'{base}.json').read_text())
    patches={'tabs':patch_tabs,'files':patch_files,'changes':patch_changes}
    staged=[]
    for node in nodes(layout):
        panel=node.get('id')
        if panel not in patches or not node.get('content',{}).get('mod'): continue
        source=node['content']['mod']
        # Replace the earlier history-owned animation with the original panel.
        if source in ('history-files','history-changes'):
            source=panel+'-i18n' if (APP/'mods'/f'{panel}-i18n').exists() else panel
        original=APP/'mods'/source
        target=APP/'mods'/f'desktop-motion-{panel}'
        text=patches[panel]((original/'main.js').read_text(), 0 if reduced else 140)
        staged.append((original,target,text))
        node['content']['mod']=target.name
    if len(staged)!=3: raise RuntimeError('需要包含 tabs、files、changes 的桌面布局')
    for original,target,text in staged:
        shutil.copytree(original,target,dirs_exist_ok=True)
        (target/'main.js').write_text(text)
        subprocess.run([str(BIN),'check',str(target)],check=True)
    layout['_motion_base']=base
    (APP/'layouts/desktop-motion-layout.json').write_text(json.dumps(layout,ensure_ascii=False,indent=2))
    layout_command(BIN, 'layout.switch', {'name':'desktop-motion-layout'})
    if any(n.get('id') == 'history-sidebar' for n in nodes(layout)):
        layout_command(BIN, 'layout.show', {'id':'history-sidebar'})
    print('已注入 Desktop Motion。原布局：'+base)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--reduce-motion',action='store_true',default=os.environ.get('HERDR_MOTION_REDUCED') == '1',help='保持性能优化，关闭过渡动画')
    args=parser.parse_args()
    install(args.reduce_motion)
