import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parent


class StatusTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        project = self.home / '.claude' / 'projects' / '-tmp-project'
        project.mkdir(parents=True)
        self.session = project / 'abc.jsonl'
        rows = [
            {'type': 'custom-title', 'customTitle': '测试会话', 'sessionId': 'abc'},
            {'type': 'ai-title', 'aiTitle': '自动标题', 'sessionId': 'abc'},
            {'type': 'permission-mode', 'permissionMode': 'plan', 'sessionId': 'abc'},
            {'type': 'assistant', 'sessionId': 'abc', 'message': {
                'model': 'group/auto[1m]',
                'usage': {'input_tokens': 200, 'cache_read_input_tokens': 120000,
                          'cache_creation_input_tokens': 0}}},
        ]
        self.session.write_text('\n'.join(json.dumps(row) for row in rows) + '\n', encoding='utf-8')

    def run_status(self, cwd='/tmp/project', title=''):
        env = dict(os.environ, HOME=str(self.home), PYTHONDONTWRITEBYTECODE='1')
        result = subprocess.run([sys.executable, '-I', str(SOURCE / 'status.py'), cwd, title],
                                env=env, text=True, capture_output=True, check=True)
        return json.loads(result.stdout)

    def test_reads_mode_context_and_title(self):
        data = self.run_status(title='测试会话')
        self.assertEqual(data['mode_label'], '计划')
        self.assertEqual(data['context'], 120200)
        self.assertEqual(data['window'], 1000000)
        self.assertEqual(data['title'], '测试会话')
        self.assertEqual(data['session'], 'abc')

    def test_falls_back_to_newest_session(self):
        data = self.run_status(title='不存在的标题')
        self.assertEqual(data['session'], 'abc')

    def test_missing_project_is_empty(self):
        self.assertEqual(self.run_status(cwd='/tmp/nowhere'), {})


if __name__ == '__main__':
    unittest.main()
