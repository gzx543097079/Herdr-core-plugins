#!/usr/bin/env python3
"""独立布局的本机插件管理后端。"""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

RUNTIME = Path(__file__).resolve().parent
PLUGINS = {'history': '对话历史', 'motion': '桌面动效', 'language': '简体中文',
           'commands': '命令提示', 'git': 'Git 工作台'}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError('无法加载运行时：' + str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def composer_module():
    composer = load_module('herdr_layout_composer', RUNTIME / 'composer.py')
    composer.motion_module = lambda: load_module('herdr_layout_motion', RUNTIME / 'desktop-motion' / 'install.py')
    return composer


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def validate_metadata(data):
    if (not isinstance(data, dict) or data.get('version') != 1
            or not isinstance(data.get('base'), dict)
            or not isinstance(data.get('rendered'), dict)
            or not isinstance(data.get('state'), dict)
            or set(data['state']) != set(PLUGINS)
            or any(type(value) is not bool for value in data['state'].values())):
        raise ValueError('布局组合元数据无效。')
    return data


def initial_metadata(app, composer):
    initial = validate_metadata(read_json(RUNTIME / 'initial.json'))
    tree = read_json(app / 'layouts' / 'herdr-plugins.json')
    base = composer.merge_changes(initial['base'], initial['rendered'], tree)
    return {'version': 1, 'state': initial['state'], 'base': base, 'rendered': tree}


def metadata(app, composer, initialize=False):
    path = app / 'plugin-controls' / 'herdr-plugins.json'
    if path.is_symlink():
        raise ValueError('布局组合元数据不能是符号链接。')
    if path.exists():
        return validate_metadata(read_json(path))
    data = initial_metadata(app, composer)
    if initialize:
        path.parent.mkdir(parents=True, exist_ok=True)
        # 先完整写入临时文件，再独占链接，避免留下半份元数据或覆盖已有文件。
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as output:
            temp = Path(output.name)
            try:
                json.dump(data, output, ensure_ascii=False)
                output.flush()
                os.fsync(output.fileno())
            except BaseException:
                temp.unlink(missing_ok=True)
                raise
        try:
            try:
                os.link(temp, path)
            except FileExistsError:
                raise RuntimeError('布局组合元数据已被其他进程创建，请重试。')
        finally:
            temp.unlink(missing_ok=True)
    return data


def store_path(app):
    return app / 'herdr-plugins-runtime'


def locked(store):
    if not store.exists():
        return False
    with (store / 'operation.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(lock, fcntl.LOCK_UN)
        return False


def last_operation(store):
    try:
        result = read_json(store / 'last-operation.json')
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError):
        return {}


def status(app):
    store = store_path(app)
    busy = locked(store)
    try:
        env = dict(os.environ, HERDR_APP_HOME=str(app))
        binary = Path.home() / '.local/bin/herdr-app'
        result = subprocess.run([str(binary), 'status'], capture_output=True, text=True,
                                timeout=30, env=env, check=True)
        data = json.loads(result.stdout)
        active = data['layout']
        managed = active == 'herdr-plugins'
        plugins = metadata(app, composer_module())['state'] if managed else {}
        return {'running': True, 'layout': active, 'errors': data.get('errors', []),
                'plugins': plugins, 'managed': managed, 'busy': busy,
                'last_operation': last_operation(store)}
    except Exception as error:
        return {'running': False, 'error': str(error), 'plugins': {}, 'busy': busy,
                'last_operation': last_operation(store)}


def save_result(store, message):
    result = {'message': message, 'id': secrets.token_hex(8)}
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=store, delete=False) as output:
        temp = Path(output.name)
        try:
            json.dump(result, output, ensure_ascii=False)
            output.flush()
            os.fsync(output.fileno())
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    try:
        os.replace(temp, store / 'last-operation.json')
    finally:
        temp.unlink(missing_ok=True)


def apply(app, plugin, action):
    before = status(app)
    if not before['running']:
        raise RuntimeError(before.get('error', '无法读取 Herdr 状态。'))
    if not before['managed']:
        raise RuntimeError('当前布局不是 herdr-plugins，无法修改插件开关。')
    composer = composer_module()
    metadata(app, composer, initialize=True)
    expected = dict(before['plugins'])
    expected[plugin] = action == 'install'
    actual = composer.compose(app, 'herdr-plugins', {plugin: action == 'install'})
    if actual != expected:
        raise RuntimeError('布局已更新，但插件状态未达到预期。')
    return PLUGINS[plugin] + ('已开启' if action == 'install' else '已关闭')


def launch(app, plugin, action):
    store = store_path(app)
    store.mkdir(parents=True, exist_ok=True)
    lock = (store / 'operation.lock').open('a')
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('已有插件操作正在执行。')
        with (store / 'operation.log').open('a', encoding='utf-8') as log:
            subprocess.Popen([sys.executable, '-I', str(Path(__file__).resolve()),
                              '--app-home', str(app), '--worker', plugin, action,
                              '--lock-fd', str(lock.fileno())], stdin=subprocess.DEVNULL,
                             stdout=log, stderr=log, start_new_session=True,
                             pass_fds=(lock.fileno(),))
    finally:
        lock.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--app-home', required=True, type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--status', action='store_true')
    group.add_argument('--launch-action', nargs=2, metavar=('PLUGIN', 'ACTION'))
    group.add_argument('--worker', nargs=2, metavar=('PLUGIN', 'ACTION'), help=argparse.SUPPRESS)
    parser.add_argument('--lock-fd', type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    app = args.app_home.expanduser().resolve()
    if args.status:
        print(json.dumps(status(app), ensure_ascii=False))
        return 0
    plugin, action = args.launch_action or args.worker
    if plugin not in PLUGINS or action not in ('install', 'uninstall'):
        parser.error('未知插件或操作。')
    if args.launch_action:
        try:
            launch(app, plugin, action)
        except (OSError, RuntimeError) as error:
            print(str(error), file=sys.stderr)
            return 1
        print('操作已开始')
        return 0
    if args.lock_fd is None:
        parser.error('缺少操作锁。')
    try:
        os.fstat(args.lock_fd)
        try:
            message = apply(app, plugin, action)
        except Exception as error:
            message = '操作失败：' + str(error)[:1200]
        save_result(store_path(app), message)
    finally:
        os.close(args.lock_fd)
    return 0


if __name__ == '__main__':
    sys.exit(main())
