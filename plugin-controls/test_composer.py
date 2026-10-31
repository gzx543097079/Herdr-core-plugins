import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('composer', Path(__file__).with_name('composer.py'))
composer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(composer)


def block(name, module):
    return {'id': name, 'type': 'block', 'content': {'mod': module}}


class ComposerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = Path(self.tmp.name)
        (self.app / 'mods').mkdir()
        (self.app / 'layouts').mkdir()
        self.path = self.app / 'layouts' / 'herdr-plugins.json'
        self.layout = {'id': 'root', 'type': 'row', 'custom': {'keep': 7}, 'children': [
            {'id': 'sidebar', 'children': [block('brand', 'workspace-chrome'), block('sidebar-footer', 'custom-footer')]},
            {'id': 'work', 'children': [block('tabs', 'tabs'), {'id': 'panel', 'size': {'px': 368}, 'max': 900, 'children': [
                {'id': 'panel-body', 'active': 'files', 'children': [block('files', 'files'), block('changes', 'changes'), block('custom-panel', 'custom')]}
            ]}, block('status', 'workspace-status')]}
        ]}
        self.write(self.app / 'layouts' / 'main.json', self.layout)
        self.write(self.path, self.layout)
        tabs = '''const enabled = shared("workspace.panels") ?? ["files", "changes"];
    this.syncPanel(space, panel, body, enabled);
    const panelButton = () => {};
      .when(w?.buttons,
'''
        for name in composer.LANG_MODS:
            for suffix in ('', '-i18n'):
                self.module(name + suffix, tabs if name == 'tabs' else ('      .child(div().flex_1())' if name == 'workspace-status' else 'source'))
        for name in ('agent-history', 'git-workbench', 'command-hints'):
            self.module(name, 'plugin')
        self.module('agent-history-tabs', '      .child(div().id("agent-history").child("history"))')
        self.motion = type('Motion', (), {name: staticmethod(lambda text, duration: text + '\nMOTION') for name in ('patch_tabs', 'patch_files', 'patch_changes')})
        patch = mock.patch.object(composer, 'motion_module', return_value=self.motion)
        patch.start()
        self.addCleanup(patch.stop)

    def write(self, path, value):
        path.write_text(json.dumps(value), encoding='utf-8')

    def module(self, name, source):
        path = self.app / 'mods' / name
        path.mkdir()
        (path / 'main.js').write_text(source, encoding='utf-8')
        (path / 'mod.json').write_text('{}', encoding='utf-8')

    def read(self):
        return json.loads(self.path.read_text(encoding='utf-8'))

    def test_all_switches_and_reversal(self):
        for feature in composer.FEATURES:
            state = composer.compose(self.app, 'herdr-plugins', {feature: True})
            self.assertTrue(state[feature])
        tree = self.read()
        self.assertEqual(composer.mod(composer.one(tree, 'history-sidebar')), 'agent-history')
        self.assertEqual(composer.mod(composer.one(tree, 'git-workbench')), 'git-workbench')
        self.assertEqual(composer.mod(composer.one(tree, 'command-hints')), 'command-hints')
        tabs = (self.app / 'mods' / composer.mod(composer.one(tree, 'tabs')) / 'main.js').read_text()
        for marker in ('agent-history', 'git-workbench', 'MOTION'):
            self.assertIn(marker, tabs)
        self.assertEqual(composer.mod(composer.one(tree, 'brand')), 'workspace-chrome-i18n')
        for feature in reversed(composer.FEATURES):
            composer.compose(self.app, 'herdr-plugins', {feature: False})
        tree = self.read()
        self.assertEqual(tree, self.layout)
        self.assertTrue((self.app / 'mods' / 'agent-history').exists())

    def test_preserves_unknown_changes_and_rejects_controlled_edit(self):
        composer.compose(self.app, 'herdr-plugins', {'history': True})
        tree = self.read()
        tree['custom']['keep'] = 9
        composer.one(tree, 'tabs')['custom'] = '保留'
        self.write(self.path, tree)
        composer.compose(self.app, 'herdr-plugins', {'git': True})
        self.assertEqual(self.read()['custom']['keep'], 9)
        self.assertEqual(composer.one(self.read(), 'tabs')['custom'], '保留')
        tree = self.read()
        composer.one(tree, 'tabs')['content']['mod'] = 'custom-tabs'
        self.write(self.path, tree)
        before = self.path.read_bytes()
        with self.assertRaises(composer.UnsupportedLayout):
            composer.compose(self.app, 'herdr-plugins', {'history': False})
        self.assertEqual(before, self.path.read_bytes())

    def test_missing_module_and_invalid_layout_are_atomic(self):
        before = self.path.read_bytes()
        (self.app / 'mods' / 'git-workbench' / 'main.js').unlink()
        with self.assertRaises(composer.UnsupportedLayout):
            composer.compose(self.app, 'herdr-plugins', {'git': True})
        self.assertEqual(before, self.path.read_bytes())
        with self.assertRaises(composer.UnsupportedLayout):
            composer.compose(self.app, '../main', {'git': True})
        with self.assertRaises(composer.UnsupportedLayout):
            composer.compose(self.app, 'herdr-plugins', {'git': 1})

    def test_adopts_existing_composed_layout(self):
        tree = copy.deepcopy(self.layout)
        composer.one(tree, 'tabs')['content']['mod'] = 'agent-history-tabs'
        composer.one(tree, 'panel-body')['children'].append({'id': 'history-sidebar', 'type': 'block', 'content': {'mod': 'agent-history', 'props': {'sidebar': True}}})
        composer.one(tree, 'panel-body')['active'] = 'history-sidebar'
        self.write(self.path, tree)
        state = composer.compose(self.app, 'herdr-plugins', {'history': False})
        self.assertFalse(state['history'])
        self.assertEqual(composer.one(self.read(), 'panel-body')['active'], 'files')


if __name__ == '__main__':
    unittest.main()
