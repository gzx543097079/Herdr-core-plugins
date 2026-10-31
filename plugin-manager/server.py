#!/usr/bin/env python3
"""Loopback-only Herdr plugin manager. No arbitrary command or filesystem endpoints."""
import argparse
import os
import json
import secrets
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
APP=Path.home()/'.config/herdr-app'
BIN=Path.home()/'.local/bin/herdr-app'
TOKEN=secrets.token_urlsafe(32)
LOCK=threading.Lock()
PLUGINS={'history': '对话历史', 'motion':'桌面动效', 'language':'简体中文', 'commands':'命令提示', 'git':'Git 工作台'}

def run(args):
    env = dict(os.environ)
    env['HERDR_PLUGIN_COMPOSE'] = '1'
    result=subprocess.run([str(a) for a in args],capture_output=True,text=True,timeout=180,env=env)
    if result.returncode: raise RuntimeError((result.stdout+'\n'+result.stderr).strip())
    return result.stdout.strip()

def layout(name):
    return json.loads((APP/'layouts'/f'{name}.json').read_text())

def chain(name):
    found=[]
    while name and name not in found:
        found.append(name)
        data=layout(name)
        name=data.get('_git_base') or data.get('_commands_base') or data.get('_motion_base') or data.get('_history_base')
    return found

def status():
    try:
        data=json.loads(run([BIN,'status'])); active=data['layout']; layers=chain(active)
        try: last=json.loads((Path.home()/'.local/share/herdr-plugins/last-operation.json').read_text())
        except (OSError,ValueError): last={}
        return {'last_operation':last,'running':True,'layout':active,'errors':data.get('errors',[]),'plugins':{
            'history':'agent-history-layout' in layers,
            'motion':'desktop-motion-layout' in layers,
            'language':'main-i18n' in layers,
            'commands':'command-hints-layout' in layers,
            'git':'git-workbench-layout' in layers},'busy':LOCK.locked()}
    except Exception as e:
        return {'running':False,'error':str(e),'plugins':{},'busy':LOCK.locked()}

def switch(name):
    return run([BIN,'do','layout.switch',json.dumps({'name':name})])

def apply_base(plugin, action):
    if plugin not in PLUGINS or action not in ('install','uninstall'): raise ValueError('未知操作')
    before=status()
    if not before['running']: raise RuntimeError('请先打开 Herdr，再刷新面板。')
    active=dict(before['plugins'])
    wanted=dict(active); wanted[plugin]=action=='install'
    # Unwind only our derived layers, then rebuild the requested composition.
    layers=chain(before['layout']); base=layers[-1]
    if base not in ('main','main-i18n') and plugin=='language':
        raise RuntimeError('当前为自定义布局；请先切换到 Herdr 主布局再修改语言插件。')
    output=[]
    try:
        if plugin=='motion':
            if action=='install':
                output.append(run([sys.executable,ROOT/'desktop-motion/install.py']))
            elif active['motion']:
                output.append(switch(layout('desktop-motion-layout')['_motion_base']))
        elif plugin=='history':
            if action=='install':
                # Its installer reapplies motion only if it was already enabled.
                output.append(run([sys.executable,ROOT/'agent-history/install.py']))
            elif active['history']:
                output.append(switch(layout('agent-history-layout')['_history_base']))
                if wanted['motion']: output.append(run([sys.executable,ROOT/'desktop-motion/install.py']))
        else:
            output.append(switch(base))
            if wanted['language']:
                output.append(run([sys.executable,ROOT/'Herdr/herdr_lang.py','install','zh-CN']))
            elif active['language']:
                output.append(run([sys.executable,ROOT/'Herdr/herdr_lang.py','uninstall']))
                output.append(switch('main'))
            if wanted['history']: output.append(run([sys.executable,ROOT/'agent-history/install.py']))
            if wanted['motion']: output.append(run([sys.executable,ROOT/'desktop-motion/install.py']))
    except Exception:
        recovery=before['layout'] if plugin!='language' else ('main-i18n' if wanted['language'] else 'main')
        try: switch(recovery)
        except Exception: pass
        raise
    after=status()
    if any(after['plugins'].get(k)!=v for k,v in wanted.items()):
        raise RuntimeError('插件状态与预期不一致，请查看 Herdr 当前布局。')
    return {'message':PLUGINS[plugin]+('已注入' if action=='install' else '已卸载'),
            'log':'\n'.join(output), 'status':after}

def apply_commands(plugin, action):
    if plugin not in PLUGINS or action not in ('install','uninstall'): raise ValueError('未知操作')
    before=status()
    if not before['running']: raise RuntimeError('请先打开 Herdr，再刷新面板。')
    hints=before['plugins'].get('commands',False)
    if plugin=='commands':
        if action=='install': log=run([sys.executable,ROOT/'command-hints/install.py'])
        elif hints: log=switch(layout('command-hints-layout')['_commands_base'])
        else: log='命令提示已停用'
        after=status()
        expected=dict(before['plugins']);expected['commands']=action=='install'
        if after['plugins']!=expected:raise RuntimeError('插件组合验证失败')
        return {'message':'命令提示'+('已注入' if action=='install' else '已卸载'),'log':log,'status':after}
    if hints: switch(layout('command-hints-layout')['_commands_base'])
    try:
        result=apply_base(plugin,action)
    finally:
        if hints: run([sys.executable,ROOT/'command-hints/install.py'])
    if hints: result['status']=status()
    return result

def apply(plugin, action):
    if plugin not in PLUGINS or action not in ('install','uninstall'):raise ValueError('未知操作')
    before=status()
    if not before['running']:raise RuntimeError('请先打开 Herdr，再刷新面板。')
    active=before['plugins'].get('git',False)
    if plugin=='git':
        if action=='install':log=run([sys.executable,ROOT/'git-workbench/install.py'])
        elif active:log=switch(layout('git-workbench-layout')['_git_base'])
        else:log='Git 工作台已停用'
        after=status();expected=dict(before['plugins']);expected['git']=action=='install'
        if after['plugins']!=expected:raise RuntimeError('插件组合验证失败')
        return {'message':'Git 工作台'+('已注入' if action=='install' else '已卸载'),'log':log,'status':after}
    if active:switch(layout('git-workbench-layout')['_git_base'])
    try:result=apply_commands(plugin,action)
    finally:
        if active:run([sys.executable,ROOT/'git-workbench/install.py'])
    if active:result['status']=status()
    return result

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def send(self,code,body,kind='application/json; charset=utf-8'):
        raw=body.encode() if isinstance(body,str) else json.dumps(body,ensure_ascii=False).encode()
        self.send_response(code);self.send_header('Content-Type',kind)
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'")
        self.end_headers();self.wfile.write(raw)
    def valid_host(self):
        return self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}'
    def do_GET(self):
        if not self.valid_host(): return self.send(403,{'error':'Invalid host'})
        if self.path=='/': return self.send(200,(Path(__file__).with_name('index.html')).read_text().replace('__TOKEN__',TOKEN),'text/html; charset=utf-8')
        if self.path=='/api/status': return self.send(200,status())
        return self.send(404,{'error':'Not found'})
    def do_POST(self):
        if not self.valid_host() or self.headers.get('X-Plugin-Token')!=TOKEN:
            return self.send(403,{'error':'请重新打开本地管理面板'})
        if self.path!='/api/action': return self.send(404,{'error':'Not found'})
        if not LOCK.acquire(False): return self.send(409,{'error':'正在处理另一个操作，请稍候'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<2048: raise ValueError('无效请求')
            data=json.loads(self.rfile.read(length)); result=apply(data.get('plugin'),data.get('action'))
            self.send(200,result)
        except Exception as e: self.send(400,{'error':str(e),'status':status()})
        finally: LOCK.release()

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--no-browser',action='store_true');parser.add_argument('--port',type=int,default=0)
    parser.add_argument('--status',action='store_true')
    parser.add_argument('--action',nargs=2,metavar=('PLUGIN','ACTION'))
    parser.add_argument('--launch-action',nargs=2,metavar=('PLUGIN','ACTION'))
    args=parser.parse_args()
    if args.status:
        print(json.dumps(status(),ensure_ascii=False));sys.exit(0)
    if args.launch_action:
        plugin, action = args.launch_action
        if plugin not in PLUGINS or action not in ('install','uninstall'): raise SystemExit('Invalid action')
        store=Path.home()/'.local/share/herdr-plugins';store.mkdir(parents=True,exist_ok=True)
        with (store/'operation.log').open('a') as log:
            subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--action',plugin,action],
                             stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
        print('操作已开始');sys.exit(0)
    if args.action:
        import time
        time.sleep(0.5)  # The launching Herdr exec must return before issuing IPC.
        store=Path.home()/'.local/share/herdr-plugins';store.mkdir(parents=True,exist_ok=True)
        import fcntl
        with (store/'operation.lock').open('w') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            try:
                result=apply(*args.action)
                (store/'last-operation.json').write_text(json.dumps({'message':result['message']},ensure_ascii=False))
                print(json.dumps(result,ensure_ascii=False))
            except Exception as e:
                (store/'last-operation.json').write_text(json.dumps({'message':'操作失败：'+str(e)[:1200]},ensure_ascii=False))
                raise
        sys.exit(0)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    url=f'http://127.0.0.1:{server.server_port}/'
    print(url,flush=True)
    if not args.no_browser: webbrowser.open(url)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
