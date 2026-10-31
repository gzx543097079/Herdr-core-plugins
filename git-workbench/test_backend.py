import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('backend',Path(__file__).with_name('backend.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class GitTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'repo';self.root.mkdir()
        self.cache=patch.object(m,'CACHE',Path(self.temp.name)/'cache');self.cache.start()
        self.git('init','-b','main');self.git('config','user.name','Plugin Test');self.git('config','user.email','test@example.invalid')
        (self.root/'one.txt').write_text('one\n');self.git('add','.');self.git('commit','-m','initial')
    def tearDown(self):self.cache.stop();self.temp.cleanup()
    def git(self,*args):return subprocess.check_output(['git','-C',str(self.root),*args],stderr=subprocess.DEVNULL,text=True).strip()
    def test_worktree_isolation_and_shared_identity(self):
        work=Path(self.temp.name)/'work';self.git('worktree','add','-b','feature',str(work))
        a=m.meta(str(self.root));b=m.meta(str(work))
        ga=m.graph(str(self.root),{});gb=m.graph(str(work),{})
        self.assertIn('HEAD -> main',next(r['refs'] for r in ga['rows'] if r.get('sha')))
        self.assertIn('HEAD -> feature',next(r['refs'] for r in gb['rows'] if r.get('sha')))
        self.assertEqual(a['common'],b['common']);self.assertNotEqual(a['gitdir'],b['gitdir']);self.assertNotEqual(a['branch'],b['branch'])
        (work/'one.txt').write_text('changed\n')
        self.assertFalse(m.changes(str(self.root))['files']);self.assertEqual(m.changes(str(work))['files'][0]['path'],'one.txt')
    def test_graph_merge_and_detail(self):
        self.git('checkout','-b','feature');(self.root/'two.txt').write_text('two\n');self.git('add','.');self.git('commit','-m','feature change')
        self.git('checkout','main');self.git('merge','--no-ff','feature','-m','merge feature')
        data=m.graph(str(self.root),{'force':True})
        commits=[r for r in data['rows'] if r.get('sha')]
        self.assertEqual(len(commits),3);self.assertEqual(len(commits[0]['parents']),2)
        detail=m.commit(str(self.root),commits[0]['sha']);self.assertIn('two.txt',[f['path'] for f in detail['files']])
        self.assertIn('+two',m.diff(str(self.root),{'sha':commits[0]['sha'],'path':'two.txt'})['text'])
        self.assertEqual(len([r for r in m.graph(str(self.root),{'query':'feature change'})['rows'] if r.get('sha')]),1)
    def test_initial_commit_and_paths(self):
        sha=self.git('rev-parse','HEAD');self.assertIn('one.txt',[f['path'] for f in m.commit(str(self.root),sha)['files']])
        name='a [1] $(not-shell).txt';(self.root/name).write_text('literal\n')
        self.assertIn('+literal',m.diff(str(self.root),{'path':name,'untracked':True})['text'])
        with self.assertRaises(ValueError):m.diff(str(self.root),{'path':'../outside','untracked':True})
        with self.assertRaises(ValueError):m.commit(str(self.root),'--help')
    def test_cache_and_remote_validation(self):
        self.assertEqual(m.github_remote('git@github.com:owner/repo.git'),'owner/repo')
        self.assertEqual(m.github_remote('https://github.com/owner/repo.git'),'owner/repo')
        self.assertIsNone(m.github_remote('https://evil.test/owner/repo'))
        calls=[]
        def read():calls.append(1);return len(calls)
        self.assertEqual(m.cached(['a'],30,False,read),1);self.assertEqual(m.cached(['a'],30,False,read),1)
        self.assertEqual(m.cached(['a'],30,True,read),2)
    def test_pr_filters_and_no_writes(self):
        with patch.object(m,'gh',return_value={'items':[],'total_count':0}) as gh:
            m.prs({'repo':'owner/repo','mode':'branch','branch':'feature/a','force':True})
            args=' '.join(gh.call_args.args);self.assertIn('head:"feature/a"',args);self.assertIn('GET',args)
        with self.assertRaises(ValueError):m.prs({'repo':'bad;command'})
    def test_branch_tracking_and_commit_comparison(self):
        first=self.git('rev-parse','HEAD')
        self.git('branch','base')
        self.git('config','branch.main.remote','.')
        self.git('config','branch.main.merge','refs/heads/base')
        (self.root/'one.txt').write_text('one\ntwo\n')
        self.git('add','.');self.git('commit','-m','second')
        second=self.git('rev-parse','HEAD')
        current=next(b for b in m.branches(str(self.root))['items'] if b['current'])
        self.assertEqual(current['name'],'main');self.assertEqual(current['ahead'],1);self.assertEqual(current['behind'],0)
        result=m.comparison(str(self.root),{'base':first,'sha':second})
        self.assertEqual(result['files'],[{'path':'one.txt'}])
        text=m.diff(str(self.root),{'base':first,'sha':second,'path':'one.txt'})['text']
        self.assertIn('+two',text)
        self.assertEqual(m.comparison(str(self.root),{'base':second,'sha':second})['files'],[])
    def test_pr_patch_pagination_binary_and_invalidation(self):
        params={'repo':'owner/repo','number':12,'path':'quote"file.txt','page':2,'head':'one'}
        with patch.object(m,'gh',return_value={'patch':'@@ -1 +1 @@\n-old\n+new','status':'modified'}) as gh:
            result=m.pr_patch(params);self.assertIn('+new',result['text'])
            self.assertIn('page=2',' '.join(gh.call_args.args));self.assertIn('quote\\"file.txt',gh.call_args.args[-1])
            m.pr_patch(params);self.assertEqual(gh.call_count,1)
            m.pr_patch(dict(params,head='two'));self.assertEqual(gh.call_count,2)
        with patch.object(m,'gh',return_value={'status':'modified'}):
            self.assertIn('未提供',m.pr_patch(dict(params,force=True))['text'])
        with patch.object(m,'gh',return_value=None):
            with self.assertRaises(ValueError):m.pr_patch(dict(params,force=True))

if __name__=='__main__':unittest.main()
