#!/usr/bin/env python3
"""汉化 Herdr 设置页（frame/settings），并随 Herdr 重写文件自动恢复。

Herdr 每次启动都会重写 frame 目录，所以直接改文件不会保留。
本模块把英文原文备份到运行时目录，改写设置页后在用户级 LaunchAgent
里监听该文件；文件变化时由 `--watch` 重新写回译文。
只处理设置页，其他 frame 和 Mod 不受影响。
"""

import argparse
import fcntl
import json
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

MARK = '// herdr-plugins-lang: injected\n'
LABEL = 'com.herdr-plugins.lang-settings'
FRAME = 'settings'
LANG = 'zh-CN'
RUNTIME = Path(__file__).resolve().parent
PACK = RUNTIME / 'lang' / f'{LANG}.json'

# 最近一次处理过的文件时间戳，避免状态轮询反复读整份源码。
_CACHE = {}


def store(app):
    return app / 'herdr-plugins-runtime'


def frame_file(app):
    return app / 'frame' / FRAME / 'main.js'


def backup_dir(app):
    return store(app) / 'frame-orig' / FRAME


def log_path(app):
    return store(app) / 'frame-lang.log'


class Locked:
    """后台任务和设置面板可能同时触发，翻译时串行执行。"""

    def __init__(self, app):
        self.path = store(app) / 'frame-lang.lock'

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open('a')
        fcntl.flock(self.handle, fcntl.LOCK_EX)
        return self

    def __exit__(self, *_):
        fcntl.flock(self.handle, fcntl.LOCK_UN)
        self.handle.close()


def table():
    try:
        pack = json.loads(PACK.read_text(encoding='utf-8'))
        return pack.get('frame') or {}
    except (OSError, ValueError):
        return {}


def replace_words(src, words):
    for en, zh in words.items():
        if en == zh:
            continue
        for quote in ('"', "'"):
            src = src.replace(f'{quote}{en}{quote}', f'{quote}{zh}{quote}')
    return src


def translate(src, frame):
    for old, new in frame.get('fragments', []):
        src = src.replace(old, new)
    return replace_words(src, frame.get('words', {}))


def original(app):
    """返回设置页英文原文：没注入过就是当前文件（并备份），否则读备份。"""
    js = frame_file(app)
    backup = backup_dir(app)
    src = js.read_text(encoding='utf-8')
    if not src.startswith(MARK):
        backup.mkdir(parents=True, exist_ok=True)
        shutil.copy2(js, backup / 'main.js')
        meta = js.parent / 'mod.json'
        if meta.exists():
            # Herdr 可能只重写 main.js；这时 mod.json 还是译文，不能覆盖英文备份。
            try:
                title = json.loads(meta.read_text(encoding='utf-8')).get('title')
            except (OSError, ValueError):
                title = None
            translated = set(table().get('titles', {}).values())
            if title not in translated:
                shutil.copy2(meta, backup / 'mod.json')
        return src
    saved = backup / 'main.js'
    return saved.read_text(encoding='utf-8') if saved.exists() else None


def apply(app):
    """把译文写回设置页；内容没变不重写。返回是否处理了设置页。"""
    js = frame_file(app)
    if not js.exists():
        return False
    frame = table()
    if not frame:
        return False
    with Locked(app):
        # 状态轮询很频繁：文件没变就直接返回，不必读整份源码。
        try:
            stamp = js.stat()
            key = (stamp.st_mtime_ns, stamp.st_size)
        except OSError:
            return False
        if _CACHE.get(str(js)) == key:
            return True
        src = original(app)
        if src is None:
            return False
        out = translate(src, frame)
        want = src if out == src else MARK + out
        if js.read_text(encoding='utf-8') != want:
            js.write_text(want, encoding='utf-8')
        saved = backup_dir(app) / 'mod.json'
        meta = js.parent / 'mod.json'
        if saved.exists() and meta.exists():
            data = json.loads(saved.read_text(encoding='utf-8'))
            title = frame.get('titles', {}).get(data.get('title'))
            if title:
                data['title'] = title
            text = json.dumps(data, ensure_ascii=False, indent=2)
            if meta.read_text(encoding='utf-8') != text:
                meta.write_text(text, encoding='utf-8')
        try:
            stamp = js.stat()
            _CACHE[str(js)] = (stamp.st_mtime_ns, stamp.st_size)
        except OSError:
            _CACHE.pop(str(js), None)
    return True


def restore(app):
    """恢复英文原文，不改动其他 frame。"""
    js = frame_file(app)
    saved = backup_dir(app) / 'main.js'
    if not saved.exists():
        return
    with Locked(app):
        if js.exists() and js.read_text(encoding='utf-8').startswith(MARK):
            shutil.copy2(saved, js)
        meta = js.parent / 'mod.json'
        saved_meta = backup_dir(app) / 'mod.json'
        if meta.exists() and saved_meta.exists():
            try:
                title = json.loads(meta.read_text(encoding='utf-8')).get('title')
            except (OSError, ValueError):
                title = None
            # 只撤销自己的译文；Herdr 新写入的标题保持原样。
            if title in set(table().get('titles', {}).values()):
                shutil.copy2(saved_meta, meta)


def plist_path():
    return Path.home() / 'Library' / 'LaunchAgents' / f'{LABEL}.plist'


def install_agent(app):
    """安装监听设置页的 LaunchAgent；重复安装时先卸载旧的。"""
    js = frame_file(app)
    if not js.exists():
        return False
    store(app).mkdir(parents=True, exist_ok=True)
    data = {
        'Label': LABEL,
        'ProgramArguments': [sys.executable, '-I', str(Path(__file__).resolve()),
                             '--app-home', str(app), '--watch'],
        'WatchPaths': [str(js)],
        'RunAtLoad': True,
        'ThrottleInterval': 2,
        'StandardOutPath': str(log_path(app)),
        'StandardErrorPath': str(log_path(app)),
    }
    target = plist_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    domain = f'gui/{os.getuid()}'
    subprocess.run(['launchctl', 'bootout', f'{domain}/{LABEL}'], capture_output=True)
    target.write_bytes(plistlib.dumps(data))
    subprocess.run(['launchctl', 'bootstrap', domain, str(target)], capture_output=True)
    return True


def uninstall_agent():
    target = plist_path()
    subprocess.run(['launchctl', 'bootout', f'gui/{os.getuid()}/{LABEL}'], capture_output=True)
    target.unlink(missing_ok=True)


def metadata_enabled(app):
    """读取插件状态：True/False；元数据不可用时返回 None。"""
    try:
        data = json.loads((app / 'plugin-controls' / 'herdr-plugins.json').read_text(encoding='utf-8'))
        value = data.get('state', {}).get('language')
        return value if type(value) is bool else None
    except (OSError, ValueError, AttributeError):
        return None


def layout_managed(app):
    """当前是否在用 herdr-plugins 布局：无法判断时返回 None。"""
    binary = Path.home() / '.local/bin/herdr-app'
    try:
        result = subprocess.run([str(binary), 'status'], capture_output=True, text=True, timeout=10,
                                env=dict(os.environ, HERDR_APP_HOME=str(app)))
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        return data['layout'] == 'herdr-plugins' if 'layout' in data else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def ensure(app):
    """状态栏刷新时自愈：译文被重写就补上，后台任务丢了就重装。"""
    if not apply(app):
        return
    if not plist_path().exists():
        install_agent(app)


def main():
    parser = argparse.ArgumentParser(description='汉化 Herdr 设置页。')
    parser.add_argument('--app-home', required=True, type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--watch', action='store_true', help='重新注入译文（后台任务用）')
    group.add_argument('--install', action='store_true', help='注入译文并安装后台任务')
    group.add_argument('--restore', action='store_true', help='恢复英文并移除后台任务')
    args = parser.parse_args()
    app = args.app_home.expanduser().resolve()
    if args.watch:
        state = metadata_enabled(app)
        if state and layout_managed(app) is False:
            # 已切到其他布局：插件不生效，恢复英文。
            state = False
        if state is False:
            # 插件已关闭或布局被移除：恢复英文并自行退出。
            uninstall_agent()
            restore(app)
            return 0
        return 0 if state and apply(app) else 1
    if args.install:
        apply(app)
        install_agent(app)
        return 0
    uninstall_agent()
    restore(app)
    return 0


if __name__ == '__main__':
    sys.exit(main())
