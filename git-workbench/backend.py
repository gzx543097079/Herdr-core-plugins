#!/usr/bin/env python3
"""Read-only Git/GitHub adapter. JSON input/output, bounded caches, no shell interpolation."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import tempfile
from pathlib import Path

CACHE = Path.home()/'.cache/herdr-git-workbench'
READ = ['--no-optional-locks','-c','core.fsmonitor=false','-c','diff.autoRefreshIndex=false']

def command(args, cwd=None, limit=2_000_000):
    env=dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_OPTIONAL_LOCKS='0', GH_PROMPT_DISABLED='1', GH_PAGER='cat', GIT_PAGER='cat', LC_ALL='C')
    # Spill Git output to temporary files so a large diff cannot fill process memory.
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        result=subprocess.run(args,cwd=cwd,env=env,stdout=out,stderr=err,timeout=22)
        if result.returncode:
            err.seek(0);raise ValueError(err.read(4000).decode('utf-8','replace').strip()[:1400] or '命令未成功完成')
        out.seek(0);return out.read(limit).decode('utf-8','replace')

def git(root,*args,limit=2_000_000):
    return command(['git',*READ,'-C',str(root),*args],limit=limit)

def github_remote(url):
    match=re.fullmatch(r'(?:https?://github\.com/|ssh://git@github\.com/|git@github\.com:)([\w.-]+/[\w.-]+?)(?:\.git)?/?',url.strip())
    return match.group(1) if match else None

def meta(cwd):
    if not cwd or not Path(cwd).is_dir(): raise ValueError('请选择一个本地仓库目录')
    try: root=git(cwd,'rev-parse','--show-toplevel').strip()
    except ValueError: raise ValueError('当前目录不是 Git 工作区，可从「仓库」选择或手动添加')
    common=git(root,'rev-parse','--path-format=absolute','--git-common-dir').strip()
    gitdir=git(root,'rev-parse','--absolute-git-dir').strip()
    try: head=git(root,'rev-parse','--verify','HEAD').strip()
    except ValueError: head=''
    try: branch=git(root,'symbolic-ref','--quiet','--short','HEAD').strip()
    except ValueError: branch='分离 HEAD'
    remotes=[]
    for name in git(root,'remote').splitlines():
        try: url=git(root,'remote','get-url',name).strip()
        except ValueError: continue
        repo=github_remote(url)
        if repo:remotes.append({'name':name,'repo':repo})
    remotes.sort(key=lambda r:r['name']!='origin')
    refs=git(root,'for-each-ref','--format=%(refname)','refs/heads','refs/remotes','refs/tags').splitlines()[:500]
    return dict(root=root,common=common,gitdir=gitdir,head=head,branch=branch,name=Path(root).name,remotes=remotes,refs=refs)

def cached(key,ttl,force,fn):
    CACHE.mkdir(parents=True,exist_ok=True)
    path=CACHE/(hashlib.sha256(json.dumps(key,sort_keys=True).encode()).hexdigest()+'.json')
    if not force:
        try:
            data=json.loads(path.read_text())
            if time.time()-data['time']<ttl:return data['value']
        except (OSError,ValueError,KeyError):pass
    value=fn()
    tmp=path.with_suffix('.'+str(os.getpid())+'.tmp')
    tmp.write_text(json.dumps({'time':time.time(),'value':value},ensure_ascii=False));tmp.replace(path)
    # A bounded number of snapshots, never histories or credentials.
    files=sorted(CACHE.glob('*.json'),key=lambda f:f.stat().st_mtime)
    for old in files[:-96]:old.unlink(missing_ok=True)
    return value

def graph(root,params):
    info=meta(root);limit=min(5000,max(100,int(params.get('limit',100))))
    scope=params.get('scope','all');query=str(params.get('query',''))[:200]
    if scope not in ('all','HEAD') and scope not in info['refs']:raise ValueError('所选分支已不存在，请刷新')
    def read():
        args=['log','--no-color','--topo-order','--date=short',f'--max-count={limit}', '--format=%x1f%H%x1f%P%x1f%an%x1f%ad%x1f%at%x1f%D%x1f%s']
        if query.startswith('author:'):args+=['--fixed-strings','--author='+query[7:]]
        elif query:args+=['--fixed-strings','--regexp-ignore-case','--grep='+query]
        args+=['--all'] if scope=='all' else [scope]
        args+=['--']
        if not info['head'] and not info['refs']:return {'rows':[],'more':False,'limit':limit}
        rows=[];commits=0
        for line in git(root,*args).splitlines():
            bits=line.split('\x1f',7)
            if len(bits)==8:
                _,sha,parents,author,date,stamp,refs,title=bits;commits+=1
                rows.append(dict(key=sha,sha=sha,parents=parents.split(),author=author,date=date,time=int(stamp or 0),refs=refs,title=title))
        return {'rows':rows,'more':commits>=limit and limit<5000,'limit':limit}
    # Decorations include worktree-specific HEAD and branch, even with --all.
    value=cached(['graph-v3',info['common'],info['gitdir'],info['head'],info['branch'],scope,query,limit],30,params.get('force'),read)
    return dict(value,meta=info)

def changes(root):
    raw=git(root,'status','--porcelain=v1','-z','--no-renames','--untracked-files=all')
    entries=[s for s in raw.split('\0') if s];rows=[]
    for s in entries[:1000]:rows.append({'path':s[3:],'status':s[:2]})
    return {'files':rows,'limited':len(entries)>1000}

def revision(value):
    if not re.fullmatch(r'[a-f0-9]{40,64}',value or ''):raise ValueError('无效提交编号')
    return value

def commit(root,sha):
    sha=revision(sha)
    text=git(root,'show','-s','--format=%B',sha,limit=16000)
    # Merge diffs are explicitly against first parent.
    files=git(root,'diff-tree','--root','-m','--first-parent','--no-commit-id','--name-only','--no-renames','-r','-z',sha).split('\0')
    return {'body':text,'files':[{'path':p} for p in dict.fromkeys(files) if p][:1000]}

def diff(root,params):
    name=params.get('path','');sha=params.get('sha','')
    if not name or Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('无效文件路径')
    pathspec=':(literal)'+name
    flags=['--no-ext-diff','--no-textconv','--no-color','--no-renames','--unified=3']
    if params.get('base'):
        text=git(root,'diff',*flags,revision(params['base']),revision(sha),'--',pathspec,limit=200001)
    elif sha:
        sha=revision(sha)
        text=git(root,'show','--format=','--first-parent',*flags,sha,'--',pathspec,limit=200001)
    elif params.get('untracked'):
        path=Path(root)/name
        if path.is_symlink():text='符号链接：'+os.readlink(path)
        elif path.is_file():
            with path.open('rb') as f: raw=f.read(200001)
            text='二进制文件，无法显示文本差异' if b'\0' in raw else ''.join('+'+line+'\n' for line in raw.decode('utf-8','replace').splitlines())
        else:text='目录或文件已不存在'
    else:
        try:git(root,'rev-parse','--verify','HEAD');has_head=True
        except ValueError:has_head=False
        text=git(root,'diff',*flags,*(['HEAD'] if has_head else []),'--',pathspec,limit=200001)
        if not has_head:text+=git(root,'diff','--cached',*flags,'--',pathspec,limit=200001)
    return {'text':text[:200000] or '无文本差异（可能是二进制、权限变化或文件已变化）','limited':len(text)>200000}

def gh(*args):
    binary=shutil.which('gh') or next((p for p in ['/opt/homebrew/bin/gh',str(Path.home()/'.local/bin/gh'),'/usr/local/bin/gh'] if Path(p).is_file()),None)
    if not binary:raise ValueError('未安装 GitHub CLI（gh）；本地提交树仍可使用')
    try:return json.loads(command([binary,*args]))
    except ValueError as e:
        message=str(e)
        if any(s in message.lower() for s in ['auth login','not logged','authentication','bad credentials']):raise ValueError('GitHub 尚未登录或授权已失效，请在终端运行 gh auth login 后刷新')
        raise

def repo_name(params):
    repo=params.get('repo','')
    if not re.fullmatch(r'[\w.-]+/[\w.-]+',repo):raise ValueError('没有可用的 GitHub remote，请先配置仓库远程地址')
    return repo

def prs(params):
    repo=repo_name(params);mode=params.get('mode','branch');branch=params.get('branch','');page=min(20,max(1,int(params.get('page',1))))
    query='repo:'+repo+' is:pr'
    if mode=='branch':
        if not branch or branch=='分离 HEAD':raise ValueError('当前工作区没有分支，请切换「全部」查看 PR')
        query+=' head:'+json.dumps(branch)
    elif mode=='mine':query+=' author:@me'
    elif mode=='review':query+=' is:open review-requested:@me'
    elif mode in ('open','closed','merged'):query+=' is:'+mode
    elif mode!='all':raise ValueError('未知 PR 筛选')
    def read():
        data=gh('api','--hostname','github.com','search/issues','--method','GET','-f','q='+query,'-f','sort=updated','-f','order=desc','-f','per_page=50','-f','page='+str(page))
        items=[]
        for p in data.get('items',[]):
            pr=p.get('pull_request',{})
            items.append(dict(number=p['number'],title=p['title'],author=p['user']['login'],url=p['html_url'],updated=p['updated_at'][:10],state='MERGED' if pr.get('merged_at') else 'DRAFT' if p.get('draft') else p['state'].upper()))
        return {'items':items,'more':page*50<min(1000,data.get('total_count',0)),'page':page}
    return cached(['prs',repo,mode,branch,page],60,params.get('force'),read)

def pr_detail(params):
    repo=repo_name(params);number=int(params.get('number',0))
    if number<1:raise ValueError('无效 PR 编号')
    def read():
        result=gh('pr','view',str(number),'--repo','https://github.com/'+repo,'--json','number,title,body,state,isDraft,url,author,baseRefName,headRefName,headRefOid,reviewDecision,statusCheckRollup,reviews')
        result['body']=result.get('body','')[:16000]
        # REST ordering is also used for lazy per-file patch paging.
        files=[]
        for page in range(1,4):
            batch=gh('api','--hostname','github.com',f'repos/{repo}/pulls/{number}/files?per_page=100&page={page}','--jq','map({path:.filename,status,additions,deletions})')
            files.extend(dict(f,page=page) for f in batch)
            if len(batch)<100:break
        result['files']=files
        result['filesLimited']=len(files)>=300
        return result
    return cached(['pr-v2',repo,number],60,params.get('force'),read)

def branches(root):
    fmt='%(refname)%00%(if)%(*objectname)%(then)%(*objectname)%(else)%(objectname)%(end)%00%(HEAD)%00%(upstream:short)%00%(upstream:track)%00%(creatordate:short)%00%(subject)'
    rows=[]
    for line in git(root,'for-each-ref','--sort=-creatordate','--format='+fmt,'refs/heads','refs/remotes','refs/tags').splitlines()[:500]:
        fields=line.split('\0',6)
        if len(fields)!=7:continue
        ref,sha,current,upstream,tracking,date,title=fields
        kind='本地分支' if ref.startswith('refs/heads/') else '远程分支' if ref.startswith('refs/remotes/') else '标签'
        ahead=re.search(r'ahead (\d+)',tracking);behind=re.search(r'behind (\d+)',tracking)
        rows.append(dict(ref=ref,sha=sha,name=ref.split('/',2)[-1],kind=kind,current=current=='*',upstream=upstream,
                         ahead=int(ahead.group(1)) if ahead else 0,behind=int(behind.group(1)) if behind else 0,
                         gone='gone' in tracking,date=date,title=title))
    return {'items':rows,'meta':meta(root)}

def comparison(root,params):
    base=revision(params.get('base'));target=revision(params.get('sha'))
    files=git(root,'diff','--no-ext-diff','--no-textconv','--no-renames','--name-only','-z',base,target,'--').split('\0')
    summary=git(root,'diff','--no-ext-diff','--no-textconv','--no-renames','--shortstat',base,target,'--').strip()
    return dict(base=base,sha=target,body=summary or '两个提交的文件内容相同',files=[{'path':f} for f in files if f][:1000])

def pr_patch(params):
    repo=repo_name(params);number=int(params.get('number',0));name=params.get('path','')
    if number<1 or not name:raise ValueError('请选择 PR 中的文件')
    # Bound network work and return only the selected patch, never a whole PR diff.
    page=max(1,min(30,int(params.get('page',1))))
    def read():
        query='map(select(.filename == '+json.dumps(name)+')) | .[0]'
        value=gh('api','--hostname','github.com',f'repos/{repo}/pulls/{number}/files?per_page=100&page={page}','--jq',query)
        if not value:raise ValueError('PR 文件列表已变化，请刷新 PR 后重试')
        patch=value.get('patch')
        text=patch if patch else 'GitHub 未提供此文件的文本补丁（可能是二进制或差异过大），请在 GitHub 查看完整差异。'
        return {'text':text[:200000],'limited':len(text)>200000,'status':value.get('status'),'additions':value.get('additions',0),'deletions':value.get('deletions',0)}
    return cached(['patch-v1',repo,number,name,params.get('head','')],60,params.get('force'),read)

def dispatch(data):
    action=data.get('action');root=data.get('cwd','')
    if action=='meta':return meta(root)
    if action=='branches':return branches(root)
    if action=='compare':return comparison(root,data)
    if action=='pr-diff':return pr_patch(data)
    if action=='graph':return graph(root,data)
    if action=='changes':return changes(root)
    if action=='commit':return commit(root,data.get('sha'))
    if action=='diff':return diff(root,data)
    if action=='prs':return prs(data)
    if action=='pr':return pr_detail(data)
    raise ValueError('未知操作')

if __name__=='__main__':
    try:result={'ok':True,'data':dispatch(json.loads(sys.argv[1]))}
    except Exception as e:result={'ok':False,'error':str(e)[:1600]}
    print(json.dumps(result,ensure_ascii=False))
