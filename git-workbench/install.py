#!/usr/bin/env python3
import json
import shutil
import subprocess
from pathlib import Path
APP=Path.home()/'.config/herdr-app';BIN=Path.home()/'.local/bin/herdr-app';SRC=Path(__file__).resolve().parent

def find(node,id):
    if isinstance(node,dict):
        if node.get('id')==id:return node
        for value in node.values():
            hit=find(value,id)
            if hit is not None:return hit
    elif isinstance(node,list):
        for value in node:
            hit=find(value,id)
            if hit is not None:return hit

def install():
    base=json.loads(subprocess.check_output([str(BIN),'status'],text=True))['layout']
    if base=='git-workbench-layout':base=json.loads((APP/'layouts/git-workbench-layout.json').read_text())['_git_base']
    layout=json.loads((APP/'layouts'/f'{base}.json').read_text());tabs=find(layout,'tabs');body=find(layout,'panel-body');panel=find(layout,'panel')
    if not tabs or not body or not panel:raise RuntimeError('当前布局不支持右侧工作台')
    target=APP/'mods/git-workbench-tabs';shutil.copytree(APP/'mods'/tabs['content']['mod'],target,dirs_exist_ok=True)
    text=(target/'main.js').read_text()
    anchor='      .child(div().id("agent-history")' if '      .child(div().id("agent-history")' in text else '      .when(w?.buttons,'
    if anchor not in text or 'const panelButton =' not in text:raise RuntimeError('标签栏结构已变化，停止注入')
    text=text.replace(anchor,'      .child(panelButton("git-workbench", "Git", "mods/git-workbench/git.svg"))\n'+anchor,1)
    text=text.replace('const enabled = ', 'const gitEnabled = ["git-workbench"];\n    const enabled = ',1)
    text=text.replace('this.syncPanel(space, panel, body, enabled);','this.syncPanel(space, panel, body, [...enabled, ...gitEnabled]);')
    (target/'main.js').write_text(text)
    mod=APP/'mods/git-workbench';mod.mkdir(exist_ok=True)
    for name in ['backend.py','mod.json','git.svg']:shutil.copy2(SRC/name,mod/name)
    (mod/'main.js').write_text((SRC/'main.js').read_text().replace('GIT_BACKEND',str(mod/'backend.py')))
    for folder in [mod,target]:subprocess.run([str(BIN),'check',str(folder)],check=True)
    tabs['content']['mod']=target.name
    body['children'].append({'id':'git-workbench','type':'block','content':{'mod':'git-workbench'}})
    panel['size']={'px':720};panel['max']=1100
    layout['_git_base']=base
    (APP/'layouts/git-workbench-layout.json').write_text(json.dumps(layout,ensure_ascii=False,indent=2))
    subprocess.run([str(BIN),'do','layout.switch',json.dumps({'name':'git-workbench-layout'})],check=True)
    print('Git 工作台已注入：点击右上角 Git 打开。')
if __name__=='__main__':install()
