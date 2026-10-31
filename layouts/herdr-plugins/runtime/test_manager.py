import fcntl
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
COMPOSER = SOURCE.parents[2] / 'plugin-controls' / 'composer.py'
FEATURES = ('history', 'motion', 'language', 'commands', 'git')


class ManagerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.runtime = self.root / 'runtime'
        self.runtime.mkdir()
        shutil.copy2(SOURCE / 'manager.py', self.runtime / 'manager.py')
        shutil.copy2(COMPOSER, self.runtime / 'composer.py')
        self.app = self.root / 'app'
        (self.app / 'layouts').mkdir(parents=True)
        self.state = dict.fromkeys(FEATURES, True)
        self.base = {'controlled': 'base', 'user': 'original'}
        self.rendered = {'controlled': 'plugin', 'user': 'original'}
        self.initial = {'version': 1, 'state': self.state, 'base': self.base,
                        'rendered': self.rendered}
        self.write(self.runtime / 'initial.json', self.initial)
        self.write(self.app / 'layouts/herdr-plugins.json', self.rendered)
        binary = self.root / '.local/bin/herdr-app'
        binary.parent.mkdir(parents=True)
        binary.write_text('#!/bin/sh\n[ "$HERDR_APP_HOME" = "' + str(self.app) + '" ] || exit 9\nprintf \'%s\\n\' \'{"layout":"herdr-plugins","errors":[]}\'\n')
        binary.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.root), PYTHONDONTWRITEBYTECODE='1')
        spec = importlib.util.spec_from_file_location('test_manager', self.runtime / 'manager.py')
        self.manager = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.manager)

    def write(self, path, value):
        path.write_text(json.dumps(value), encoding='utf-8')

    def cli(self, *args):
        return subprocess.run([sys.executable, '-I', str(self.runtime / 'manager.py'),
                               '--app-home', str(self.app), *args], env=self.env,
                              text=True, capture_output=True, timeout=10)

    def test_status_and_initial_merge(self):
        self.write(self.app / 'layouts/herdr-plugins.json',
                   {'controlled': 'plugin', 'user': 'changed'})
        response = self.cli('--status')
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertEqual(json.loads(response.stdout)['plugins'], self.state, response.stdout)
        self.assertFalse((self.app / 'plugin-controls').exists())
        composer = self.manager.composer_module()
        metadata = self.manager.metadata(self.app, composer, initialize=True)
        self.assertEqual(metadata['base']['user'], 'changed')
        self.assertEqual(metadata['rendered']['user'], 'changed')

    def test_conflict_does_not_initialize(self):
        self.write(self.app / 'layouts/herdr-plugins.json',
                   {'controlled': 'modified', 'user': 'original'})
        with self.assertRaises(ValueError):
            self.manager.metadata(self.app, self.manager.composer_module(), initialize=True)
        self.assertFalse((self.app / 'plugin-controls/herdr-plugins.json').exists())

    def test_invalid_metadata_never_overwritten(self):
        path = self.app / 'plugin-controls/herdr-plugins.json'
        path.parent.mkdir()
        path.write_text('{broken')
        with self.assertRaises(ValueError):
            self.manager.metadata(self.app, self.manager.composer_module(), initialize=True)
        self.assertEqual(path.read_text(), '{broken')

    def test_other_layout_is_unmanaged(self):
        binary = self.root / '.local/bin/herdr-app'
        binary.write_text('#!/bin/sh\nprintf \'%s\\n\' \'{"layout":"main"}\'\n')
        result = json.loads(self.cli('--status').stdout)
        self.assertTrue(result['running'])
        self.assertFalse(result['managed'])
        self.assertEqual(result['plugins'], {})

    def test_asynchronous_success(self):
        with (self.runtime / 'composer.py').open('a') as output:
            output.write('''\n\ndef compose(app, layout_name, changes):
    import json
    path = app / 'plugin-controls' / 'herdr-plugins.json'
    data = json.loads(path.read_text())
    data['state'].update(changes)
    path.write_text(json.dumps(data))
    return data['state']
''')
        response = self.cli('--launch-action', 'history', 'uninstall')
        self.assertEqual(response.returncode, 0, response.stderr)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = json.loads(self.cli('--status').stdout)
            if result['last_operation'] and not result['busy']:
                break
            time.sleep(.03)
        self.assertEqual(result['last_operation']['message'], '对话历史已关闭')
        self.assertFalse(result['plugins']['history'])

    def test_asynchronous_failure_and_lock(self):
        store = self.app / 'herdr-plugins-runtime'
        store.mkdir()
        with (store / 'operation.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertTrue(json.loads(self.cli('--status').stdout)['busy'])
            self.assertNotEqual(self.cli('--launch-action', 'history', 'uninstall').returncode, 0)
        response = self.cli('--launch-action', 'history', 'uninstall')
        self.assertEqual(response.returncode, 0, response.stderr)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = json.loads(self.cli('--status').stdout)
            if result['last_operation'] and not result['busy']:
                break
            time.sleep(.03)
        self.assertTrue(result['last_operation']['message'].startswith('操作失败：'))
        self.assertTrue(result['last_operation']['id'])


if __name__ == '__main__':
    unittest.main()
