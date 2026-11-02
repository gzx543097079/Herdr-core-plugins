import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('test_history', SOURCE / 'history.py')
history = importlib.util.module_from_spec(spec)
spec.loader.exec_module(history)


class TitleTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'session.jsonl'

    def write(self, rows):
        with self.path.open('w', encoding='utf-8') as output:
            for row in rows:
                output.write(json.dumps(row, ensure_ascii=False) + '\n')

    def user(self, text, **extra):
        return {'type': 'user', 'sessionId': 's1', 'cwd': '/tmp/project',
                'message': {'content': text}, **extra}

    def test_custom_title_wins(self):
        self.write([
            self.user('/model'),
            self.user('真正的第一句话'),
            {'type': 'ai-title', 'aiTitle': '自动标题'},
            {'type': 'custom-title', 'customTitle': '用户命名的标题'},
        ])
        self.assertEqual(history.parse(self.path, 'Claude', 1)['title'], '用户命名的标题')

    def test_ai_title_beats_first_prompt(self):
        self.write([self.user('真正的第一句话'),
                    {'type': 'ai-title', 'aiTitle': '自动标题'}])
        self.assertEqual(history.parse(self.path, 'Claude', 1)['title'], '自动标题')

    def test_last_custom_title_wins(self):
        self.write([self.user('问题'),
                    {'type': 'custom-title', 'customTitle': '旧名'},
                    {'type': 'custom-title', 'customTitle': '新名'}])
        self.assertEqual(history.parse(self.path, 'Claude', 1)['title'], '新名')

    def test_skips_commands_and_system_messages(self):
        self.write([
            self.user('<command-name>/model</command-name>\n<command-args></command-args>'),
            self.user('<local-command-stdout>Set model</local-command-stdout>'),
            self.user('<local-command-caveat>note</local-command-caveat>'),
            self.user('真正的第一句话'),
        ])
        self.assertEqual(history.parse(self.path, 'Claude', 1)['title'], '真正的第一句话')

    def test_skips_meta_and_sidechain(self):
        self.write([
            self.user('子代理消息', isSidechain=True),
            self.user('元消息', isMeta=True),
            self.user('主对话'),
        ])
        self.assertEqual(history.parse(self.path, 'Claude', 1)['title'], '主对话')

    def test_returns_none_without_prompt(self):
        self.write([self.user('<command-name>/model</command-name>')])
        self.assertIsNone(history.parse(self.path, 'Claude', 1))

    def test_handoff_title_display(self):
        self.assertEqual(history.display_title('导入对话标题：示例\n以下是从其他 CLI 导入的历史对话文本'),
                         '示例')


if __name__ == '__main__':
    unittest.main()
