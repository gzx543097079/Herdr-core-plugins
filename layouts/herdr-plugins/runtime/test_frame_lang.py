import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

SOURCE = Path(__file__).resolve().parent
MODE_RUNTIME = SOURCE.parent / 'mods' / 'plugin-controls' / 'runtime'
COMPOSER = SOURCE.parents[2] / 'plugin-controls' / 'composer.py'
FEATURES = ('history', 'motion', 'language', 'commands', 'git')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FrameLangTest(unittest.TestCase):
    def setUp(self):
        self.frame = load('test_frame_lang', MODE_RUNTIME / 'frame_lang.py')
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.app = Path(temp.name).resolve()
        self.settings = self.app / 'frame' / 'settings'
        self.settings.mkdir(parents=True)
        self.original = (
            'const LOOKS = { main: "Herdr" };\n'
            'v_flex().child(this.heading(t, "Keyboard"))\n'
            '  .child(this.row(t, "Theme", "Reset"))\n'
            '  .child(this.heading(t, "Appearance"));\n'
        )
        self.write_original()

    def write_original(self):
        (self.settings / 'main.js').write_text(self.original, encoding='utf-8')
        (self.settings / 'mod.json').write_text(
            json.dumps({'place': 'none', 'title': 'Settings'}), encoding='utf-8')

    def test_apply_and_restore(self):
        self.assertTrue(self.frame.apply(self.app))
        text = (self.settings / 'main.js').read_text(encoding='utf-8')
        self.assertTrue(text.startswith(self.frame.MARK))
        for word in ('键盘', '主题', '重置', '明暗模式'):
            self.assertIn(word, text)
        self.assertNotIn('"Keyboard"', text)
        self.assertEqual(json.loads((self.settings / 'mod.json').read_text())['title'], '设置')
        patched = text

        # 重复注入不改变内容
        self.frame.apply(self.app)
        self.assertEqual((self.settings / 'main.js').read_text(encoding='utf-8'), patched)

        self.frame.restore(self.app)
        self.assertEqual((self.settings / 'main.js').read_text(encoding='utf-8'), self.original)
        self.assertEqual(json.loads((self.settings / 'mod.json').read_text())['title'], 'Settings')

    def test_apply_after_herdr_rewrite(self):
        self.frame.apply(self.app)
        patched = (self.settings / 'main.js').read_text(encoding='utf-8')
        # Herdr 只重写 main.js，mod.json 仍是译文
        (self.settings / 'main.js').write_text(self.original, encoding='utf-8')
        self.assertTrue(self.frame.apply(self.app))
        self.assertEqual((self.settings / 'main.js').read_text(encoding='utf-8'), patched)
        self.frame.restore(self.app)
        self.assertEqual(json.loads((self.settings / 'mod.json').read_text())['title'], 'Settings')

    def test_restore_after_main_rewrite(self):
        """Herdr 重写 main.js 后关闭开关，标题仍应恢复英文。"""
        self.frame.apply(self.app)
        (self.settings / 'main.js').write_text(self.original, encoding='utf-8')
        self.frame.restore(self.app)
        self.assertEqual(json.loads((self.settings / 'mod.json').read_text())['title'], 'Settings')
        self.assertEqual((self.settings / 'main.js').read_text(encoding='utf-8'), self.original)

    def test_missing_frame_is_skipped(self):
        shutil.rmtree(self.app / 'frame')
        self.assertFalse(self.frame.apply(self.app))

    def test_metadata_enabled(self):
        self.assertIsNone(self.frame.metadata_enabled(self.app))
        path = self.app / 'plugin-controls' / 'herdr-plugins.json'
        path.parent.mkdir()
        path.write_text(json.dumps({'state': {'language': True}}))
        self.assertTrue(self.frame.metadata_enabled(self.app))
        path.write_text(json.dumps({'state': {'language': False}}))
        self.assertFalse(self.frame.metadata_enabled(self.app))

    def test_pack_matches_language_source(self):
        """插件内置语言包必须与 Herdr/lang/zh-CN.json 的 frame 表一致。"""
        plugin = json.loads((MODE_RUNTIME / 'lang' / 'zh-CN.json').read_text(encoding='utf-8'))
        source = json.loads((SOURCE.parents[2] / 'Herdr' / 'lang' / 'zh-CN.json')
                            .read_text(encoding='utf-8'))
        self.assertEqual(plugin['frame'], source['frame'])

    def test_watch_restores_after_leaving_layout(self):
        self.frame.apply(self.app)
        meta = self.app / 'plugin-controls' / 'herdr-plugins.json'
        meta.parent.mkdir()
        meta.write_text(json.dumps({'state': {'language': True}}))
        self.frame.layout_managed = lambda app: False
        self.frame.uninstall_agent = lambda: None
        old = sys.argv
        sys.argv = ['frame_lang.py', '--app-home', str(self.app), '--watch']
        try:
            self.assertEqual(self.frame.main(), 0)
        finally:
            sys.argv = old
        self.assertEqual((self.settings / 'main.js').read_text(encoding='utf-8'), self.original)


class ManagerLanguageTest(unittest.TestCase):
    """简体中文开关应带动设置页汉化。"""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.runtime = self.root / 'runtime'
        self.runtime.mkdir()
        shutil.copy2(SOURCE / 'manager.py', self.runtime / 'manager.py')
        shutil.copy2(COMPOSER, self.runtime / 'composer.py')
        with (self.runtime / 'composer.py').open('a') as output:
            output.write(FAKE_COMPOSER)
        (self.runtime / 'frame_lang.py').write_text(FAKE_FRAME, encoding='utf-8')
        self.app = self.root / 'app'
        (self.app / 'layouts').mkdir(parents=True)
        self.log = self.root / 'frame.log'
        self.write(self.runtime / 'initial.json', {
            'version': 1, 'state': dict.fromkeys(FEATURES, False),
            'base': {}, 'rendered': {}})
        self.write(self.app / 'layouts/herdr-plugins.json', {})
        meta = self.app / 'plugin-controls' / 'herdr-plugins.json'
        meta.parent.mkdir(parents=True)
        self.write(meta, {'version': 1, 'state': dict.fromkeys(FEATURES, False),
                          'base': {}, 'rendered': {}})
        binary = self.root / '.local/bin/herdr-app'
        binary.parent.mkdir(parents=True)
        binary.write_text('#!/bin/sh\nprintf \'%s\\n\' \'{"layout":"herdr-plugins","errors":[]}\'\n')
        binary.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.root), PYTHONDONTWRITEBYTECODE='1',
                        FRAME_TEST_LOG=str(self.log))

    def write(self, path, value):
        path.write_text(json.dumps(value), encoding='utf-8')

    def calls(self):
        return self.log.read_text(encoding='utf-8').split() if self.log.exists() else []

    def toggle(self, action):
        response = subprocess.run([sys.executable, '-I', str(self.runtime / 'manager.py'),
                                   '--app-home', str(self.app), '--launch-action', 'language', action],
                                  env=self.env, text=True, capture_output=True, timeout=10)
        self.assertEqual(response.returncode, 0, response.stderr)
        deadline = time.monotonic() + 5
        result = {}
        while time.monotonic() < deadline:
            result = json.loads(subprocess.run(
                [sys.executable, '-I', str(self.runtime / 'manager.py'),
                 '--app-home', str(self.app), '--status'],
                env=self.env, text=True, capture_output=True, timeout=10).stdout)
            if result['last_operation'] and not result['busy']:
                break
            time.sleep(.03)
        return result

    def test_install_and_uninstall(self):
        result = self.toggle('install')
        self.assertEqual(result['last_operation']['message'], '简体中文已开启')
        self.assertEqual(self.calls(), ['apply', 'install_agent'])
        self.assertTrue(result['plugins']['language'])

        self.log.unlink()
        result = self.toggle('uninstall')
        self.assertEqual(result['last_operation']['message'], '简体中文已关闭')
        self.assertEqual(self.calls(), ['uninstall_agent', 'restore'])
        self.assertFalse(result['plugins']['language'])

    def test_other_plugin_does_not_touch_frame(self):
        response = subprocess.run([sys.executable, '-I', str(self.runtime / 'manager.py'),
                                   '--app-home', str(self.app), '--launch-action', 'history', 'install'],
                                  env=self.env, text=True, capture_output=True, timeout=10)
        self.assertEqual(response.returncode, 0, response.stderr)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = json.loads(subprocess.run(
                [sys.executable, '-I', str(self.runtime / 'manager.py'),
                 '--app-home', str(self.app), '--status'],
                env=self.env, text=True, capture_output=True, timeout=10).stdout)
            if result['last_operation'] and not result['busy']:
                break
            time.sleep(.03)
        self.assertFalse(self.log.exists())


FAKE_FRAME = '''
import json
import os
from pathlib import Path


def _note(name):
    path = Path(os.environ['FRAME_TEST_LOG'])
    with path.open('a', encoding='utf-8') as output:
        output.write(name + '\\n')


def apply(app):
    _note('apply')
    return True


def install_agent(app):
    _note('install_agent')
    return True


def uninstall_agent():
    _note('uninstall_agent')


def restore(app):
    _note('restore')
'''

FAKE_COMPOSER = '''

def compose(app, layout_name, changes):
    import json
    path = app / 'plugin-controls' / 'herdr-plugins.json'
    data = json.loads(path.read_text())
    data['state'].update(changes)
    path.write_text(json.dumps(data))
    return data['state']
'''


if __name__ == '__main__':
    unittest.main()
