#!/usr/bin/env python3
"""Read bounded user/project Skill headers only; never execute Skill instructions."""
import json
from itertools import islice
import re
import sys
from pathlib import Path

def collect(agent, cwd, home=None):
    home=Path(home or Path.home()); project=Path(cwd) if cwd else None
    roots=[]
    if agent=='Claude':
        if project: roots += [(project/'.claude/skills',False),(project/'.claude/commands',True)]
        roots += [(home/'.claude/skills',False),(home/'.claude/commands',True)]
    else:
        if project: roots += [(project/'.agents/skills',False),(project/'.codex/skills',False)]
        roots += [(home/'.agents/skills',False),(home/'.codex/skills',False),(home/'.codex/skills/.system',False)]
    found={}
    for root,legacy in roots:
        try: entries=sorted(islice(root.iterdir(),500))
        except OSError: continue
        for entry in entries:
            if entry.name.startswith('.'): continue
            path=entry if legacy and entry.suffix=='.md' else entry/'SKILL.md'
            try:
                if not path.is_file():continue
                with path.open() as f: header=f.read(8192)
            except (OSError,UnicodeError):continue
            metadata=header.split('---',2)[1] if header.startswith('---') and header.count('---')>=2 else ''
            if re.search(r'^user-invocable:\s*false\s*$',metadata,re.M):continue
            name=entry.stem if legacy else entry.name
            match=re.search(r'^name:\s*[\'"]?([\w:-]+)',metadata,re.M)
            if match:name=match.group(1)
            if not re.fullmatch(r'[\w:-]+',name):continue
            description=re.search(r'^description:\s*(.+)',metadata,re.M)
            command=('/' if agent=='Claude' else '$')+name
            found.setdefault(command,{'command':command,'description':description.group(1).strip(' \"\'')[:140] if description else '本地 Skill'})
    return sorted(found.values(),key=lambda row:row['command'])

if __name__=='__main__':
    if len(sys.argv)<2 or sys.argv[1] not in ('Claude','Codex'):raise SystemExit('需要 Claude 或 Codex')
    print(json.dumps(collect(sys.argv[1],sys.argv[2] if len(sys.argv)>2 else ''),ensure_ascii=False))
