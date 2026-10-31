import importlib.util
from pathlib import Path
import tempfile
import unittest
spec=importlib.util.spec_from_file_location('skills',Path(__file__).with_name('skills.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class SkillTests(unittest.TestCase):
    def test_scopes_dedup_hidden_and_legacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)/'home';project=Path(tmp)/'project'
            for root,desc in [(home,'global'),(project,'project')]:
                path=root/'.claude/skills/demo/SKILL.md';path.parent.mkdir(parents=True)
                path.write_text('---\nname: demo\ndescription: '+desc+'\n---\n')
            hidden=home/'.claude/skills/hidden/SKILL.md';hidden.parent.mkdir(parents=True);hidden.write_text('---\nuser-invocable: false\n---\n')
            legacy=home/'.claude/commands/old.md';legacy.parent.mkdir(parents=True);legacy.write_text('prompt')
            rows=m.collect('Claude',project,home)
            self.assertEqual([r['command'] for r in rows],['/demo','/old'])
            self.assertEqual(rows[0]['description'],'project')
            self.assertEqual(m.collect('Codex',project,home),[])
    def test_codex_symlink_and_missing_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp);source=home/'source';source.mkdir();(source/'SKILL.md').write_text('---\nname: linked\n---')
            root=home/'.codex/skills';root.mkdir(parents=True);(root/'link').symlink_to(source)
            self.assertEqual(m.collect('Codex','',home)[0]['command'],'$linked')
if __name__=='__main__':unittest.main()
