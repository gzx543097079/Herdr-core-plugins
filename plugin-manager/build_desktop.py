#!/usr/bin/env python3
import plistlib
import shutil
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
STORE=Path.home()/'.local/share/herdr-plugins'
# Remove only the old settings-manager hook, before restoring full Chinese.
subprocess.run(['/usr/bin/python3',str(ROOT/'plugin-manager/settings_integration.py'),'uninstall'],check=True)
for name in ('agent-history','desktop-motion','command-hints','git-workbench','Herdr','plugin-manager'):
    shutil.copytree(ROOT/name,STORE/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
bundle=ROOT/'Herdr 插件管理.app'
binary=bundle/'Contents/MacOS/HerdrPluginManager';binary.parent.mkdir(parents=True,exist_ok=True)
source=ROOT/'plugin-manager/desktop/main.swift'
if not binary.exists() or source.stat().st_mtime>binary.stat().st_mtime:
    subprocess.run(['xcrun','swiftc',str(source),'-o',str(binary),'-framework','AppKit'],check=True)
(bundle/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleExecutable':binary.name,'CFBundleIdentifier':'local.herdr.pluginmanager','CFBundleName':'Herdr 插件管理','CFBundlePackageType':'APPL','NSHighResolutionCapable':True,'LSMinimumSystemVersion':'12.0'}))
print(bundle)
