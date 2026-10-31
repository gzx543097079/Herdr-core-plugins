"""Reversible settings hook. App bundle and shipped mods remain untouched."""
import json
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
STORE=Path.home()/'.local/share/herdr-plugins'
APP=Path.home()/'.config/herdr-app'
TARGET=APP/'frame/settings/main.js'
MARK='// herdr-plugin-manager: injected\n'
LABEL='com.herdr-plugins.settings'
PLIST=Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist'

def inject():
    if not TARGET.exists(): return False
    current=TARGET.read_text()
    if current.startswith(MARK):
        original=(STORE/'settings-original.js').read_text()
    else:
        original=current
    code=original
    replacements=[
      ('import { hc,', 'import { exec, hc,'),
      ('const SECTIONS = [', 'const HERDR_PLUGIN_MANAGER = '+json.dumps(str(STORE/'plugin-manager/server.py'))+';\nconst SECTIONS = [\n  { id: "plugins", title: "插件", icon: "server" },'),
      ('    this.person = {};', '    this.pluginState = null; this.pluginBusy = false; this.pluginNotice = "";\n    this.loadPluginState(cx);\n    this.person = {};'),
      ('  file() {', (ROOT/'plugin-manager/settings-methods.js').read_text()+'\n  file() {'),
      ('this.section === "look"\n', 'this.section === "plugins" ? this.pluginManager(t) : this.section === "look"\n'),
    ]
    for old,new in replacements:
        if old not in code: raise RuntimeError('设置页结构已变化，未注入插件管理：'+old[:40])
        code=code.replace(old,new,1)
    desired=MARK+code
    if current==desired:return False
    STORE.mkdir(parents=True,exist_ok=True)
    (STORE/'settings-original.js').write_text(original)
    # Validate in a separate mod before touching the generated settings view.
    test=STORE/'settings-check'; test.mkdir(exist_ok=True)
    (test/'main.js').write_text(desired)
    shutil.copy2(TARGET.parent/'mod.json',test/'mod.json')
    subprocess.run([str(Path.home()/'.local/bin/herdr-app'),'check',str(test)],check=True,capture_output=True,text=True)
    tmp=TARGET.with_suffix('.plugin-tmp');tmp.write_text(desired);tmp.replace(TARGET)
    return True

def install():
    if ROOT != STORE:
        for name in ('agent-history','desktop-motion','Herdr','plugin-manager'):
            shutil.copytree(ROOT/name,STORE/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    inject()
    # One event-driven hook, no polling. A no-change pass writes nothing.
    data={'Label':LABEL,'ProgramArguments':['/usr/bin/python3',str(STORE/'plugin-manager/settings_integration.py'),'refresh'],
          'WatchPaths':[str(TARGET)],'RunAtLoad':True,'ThrottleInterval':10,
          'StandardOutPath':str(STORE/'settings-hook.log'),'StandardErrorPath':str(STORE/'settings-hook.log')}
    PLIST.parent.mkdir(parents=True,exist_ok=True)
    PLIST.write_bytes(plistlib.dumps(data))
    domain=f'gui/{os.getuid()}'
    subprocess.run(['launchctl','bootout',f'{domain}/{LABEL}'],capture_output=True)
    subprocess.run(['launchctl','bootstrap',domain,str(PLIST)],check=True,capture_output=True)
    print('已注入：Herdr 设置 → 插件')

def uninstall():
    subprocess.run(['launchctl','bootout',f'gui/{os.getuid()}/{LABEL}'],capture_output=True)
    PLIST.unlink(missing_ok=True)
    if TARGET.exists() and TARGET.read_text().startswith(MARK):
        TARGET.write_text((STORE/'settings-original.js').read_text())

if __name__=='__main__':
    action=sys.argv[1] if len(sys.argv)>1 else 'install'
    if action=='install':install()
    elif action=='refresh':inject()
    elif action=='uninstall':uninstall()
    else:raise SystemExit('Unknown action')
