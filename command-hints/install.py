#!/usr/bin/env python3

# 独立运行时交给管理器组合布局；管理器调用时执行下方实际安装逻辑。
if __name__ == '__main__':
    import os
    import sys
    from pathlib import Path
    if os.environ.get('HERDR_PLUGIN_COMPOSE') != '1':
        if len(sys.argv) != 1:
            raise SystemExit('用法：install.py')
        manager = Path(__file__).resolve().parent.parent / 'plugin-manager/server.py'
        os.execv(sys.executable, [sys.executable, str(manager), '--action', 'commands', 'install'])

import json
import shutil
import subprocess
from pathlib import Path
APP=Path.home()/'.config/herdr-app'; BIN=Path.home()/'.local/bin/herdr-app'; SRC=Path(__file__).resolve().parent

def find(value,id):
    if isinstance(value,dict):
        if value.get('id')==id:return value
        for child in value.values():
            found=find(child,id)
            if found is not None:return found
    elif isinstance(value,list):
        for child in value:
            found=find(child,id)
            if found is not None:return found

def install():
    state=json.loads(subprocess.check_output([str(BIN),'status'],text=True));base=state['layout']
    if base=='command-hints-layout':base=json.loads((APP/'layouts/command-hints-layout.json').read_text())['_commands_base']
    layout=json.loads((APP/'layouts'/f'{base}.json').read_text())
    status=find(layout,'status'); work=find(layout,'work')
    if not status or not work:raise RuntimeError('当前布局没有底部状态栏')
    mod=APP/'mods/command-hints';mod.mkdir(exist_ok=True)
    shutil.copy2(SRC/'mod.json',mod/'mod.json');[shutil.copy2(f,mod/f.name) for f in SRC.glob('*.svg')];shutil.copy2(SRC/'skills.py',mod/'skills.py')
    (mod/'main.js').write_text((SRC/'main.js').read_text().replace('SKILLS_SCRIPT',str(mod/'skills.py')))
    target=APP/'mods/command-hints-status';shutil.copytree(APP/'mods'/status['content']['mod'],target,dirs_exist_ok=True)
    source=(target/'main.js').read_text();anchor='      .child(div().flex_1())'
    if anchor not in source:raise RuntimeError('状态栏结构变化，停止注入')
    source=source.replace(anchor,anchor+'''\n      .child(div().id("command-hints-toggle").px(8).h(24).flex().items_center().rounded(5).cursor_pointer().hover(s=>s.bg(t.hover)).on_click(()=>run("layout.toggle",{id:"command-hints"})).child("命令提示"))''',1)
    (target/'main.js').write_text(source);status['content']['mod']=target.name
    index=work['children'].index(status)
    work['children'].insert(index,{'id':'command-hints','type':'block','content':{'mod':'command-hints'},'size':{'px':185},'min':175,'max':440,'hidden':True})
    layout['_commands_base']=base
    for p in (mod,target):subprocess.run([str(BIN),'check',str(p)],check=True)
    (APP/'layouts/command-hints-layout.json').write_text(json.dumps(layout,ensure_ascii=False,indent=2))
    subprocess.run([str(BIN),'do','layout.switch',json.dumps({'name':'command-hints-layout'})],check=True)
    print('命令提示已注入：点击底部「命令提示」手动展开。')
if __name__=='__main__':install()
