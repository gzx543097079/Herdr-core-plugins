import { View, div, svg, PathBuilder } from 'gpui-kit';
import { v_flex, h_flex, InputState, Input, v_virtual_list, Scrollbar } from 'gpui-base';
import { exec, run, theme, focused, panes, spaces, layout, watchFolder } from 'herdr';

const basename = p => (p || '').split('/').filter(Boolean).pop() || p;
const find = (node,id) => node?.id===id ? node : (node?.children || []).map(n=>find(n,id)).find(Boolean);
const shown = () => !find(layout(),'panel')?.hidden && find(layout(),'panel-body')?.active==='git-workbench';
const W='mods/workspace-chrome/',G='mods/git-workbench/';
const I={down:W+'chevron-down.svg',branch:W+'git-branch.svg',tag:G+'tag.svg',folder:W+'folder.svg',pin:W+'pin.svg',pinOff:W+'pin-off.svg',x:W+'x.svg',search:W+'search.svg',check:W+'check.svg',compare:W+'git-compare.svg',refresh:G+'refresh.svg',max:G+'maximize.svg',min:G+'minimize.svg',ext:G+'external.svg',copy:G+'copy.svg'};
const states = {OPEN:'打开',CLOSED:'已关闭',MERGED:'已合并',DRAFT:'草稿'};
function source() {
  const f=focused(), all=panes(), active=spaces().find(s=>s.active);
  const pane=f?.pane ? all.find(p=>p.pane===f.pane) : null, space=spaces().find(s=>s.tabs?.some(t=>t.id===pane?.tab)) || active;
  const cwd=pane?.cwd || f?.cwd || space?.folder;
  if(!cwd)return null;
  const on=f?.terminal?.includes('/') ? f.terminal.split('/')[0] : space?.machine || null;
  return {cwd, pane:f?.pane || null, on, label:pane ? '终端 '+(all.indexOf(pane)+1)+' · '+basename(pane.cwd) : (space?.name ? '空间 '+space.name : '当前终端')};
}
const H=46,LANE=14,lx=i=>10+i*LANE;
// 按父提交分配泳道：每列记住它在等待的下一个提交，节点处汇合或分叉。
function layoutGraph(rows,head,dirty,flat){
  const list=rows.filter(r=>r.sha);
  if(dirty)list.unshift({key:'__dirty',sha:'__dirty',parents:head?[head]:[],dirty:true});
  const lanes=[];let max=1;
  const out=list.map(r=>{
    if(flat)return {...r,col:0,before:[],targets:[],head:r.sha===head};
    const before=lanes.slice();let col=lanes.indexOf(r.sha);
    if(col<0){col=lanes.indexOf(null);if(col<0)col=lanes.length;}
    for(let i=0;i<lanes.length;i++)if(lanes[i]===r.sha)lanes[i]=null;
    const ps=r.parents||[],targets=[];
    lanes[col]=ps[0]??null;if(ps[0])targets.push(col);
    for(const p of ps.slice(1)){let k=lanes.indexOf(p);if(k<0){k=lanes.indexOf(null);if(k<0)k=lanes.length;lanes[k]=p;}targets.push(k);}
    while(lanes.length&&lanes[lanes.length-1]==null)lanes.pop();
    max=Math.max(max,before.length,lanes.length,col+1);
    return {...r,col,before,targets,head:r.sha===head};
  });
  return {rows:out,max};
}
function ago(time,date){
  if(!time)return date||'';
  const s=Math.max(0,Date.now()/1000-time);
  if(s<60)return '刚刚';if(s<3600)return Math.floor(s/60)+' 分钟前';if(s<86400)return Math.floor(s/3600)+' 小时前';if(s<86400*7)return Math.floor(s/86400)+' 天前';
  const d=new Date(time*1000),now=new Date();return (d.getFullYear()===now.getFullYear()?'':d.getFullYear()+'年')+(d.getMonth()+1)+'月'+d.getDate()+'日';
}
export default class GitWorkbench extends View {
  init(_p,cx) {
    this.width=760;this.height=700;this.branches=[];this.base=null;this.note='';this.detailTab='files';this.detailOnly=false;this.contextSerial=0;this.detailToken=0;this.fileToken=0;this.target=null;this.context='';this.epoch=0;this.tab='graph';this.fixed=false;this.info=null;
    this.graph=[];this.dirty=[];this.prs=[];this.detail=null;this.diff=[];this.error='';this.loading=false;
    this.scope='all';this.query='';this.limit=100;this.prMode='branch';this.prPage=1;this.more=false;
    this.known=[];this.repoPicker=false;this.branchPicker=false;this.remoteIndex=0;this.watchers=new Set();this.cache=new Map();
    this.search=InputState.new({placeholder:'搜索提交说明；author:名字 搜索作者'});
    this.search.on('change',(_e,cx)=>{const generation=++this.searchGeneration;cx.timer.after(300,cx=>{if(generation!==this.searchGeneration || !shown())return;this.query=this.search.value();this.limit=100;this.load(cx);});});
    this.searchGeneration=0;
    this.pathInput=InputState.new({placeholder:'输入本地仓库路径，按回车添加'});
    this.pathInput.on('submit',(_e,cx)=>{const cwd=this.pathInput.value().trim();if(cwd){this.fixed=true;this.repoPicker=false;this.activate({cwd,on:null,pane:null,label:'手动选择'},cx);}});
  }
  async call(action,params={}) {
    const r=await exec('/usr/bin/python3',['-I','GIT_BACKEND',JSON.stringify({action,...params})]);
    if(r.code!==0)throw new Error(r.stderr || '读取失败');
    const value=JSON.parse(r.stdout);if(!value.ok)throw new Error(value.error);return value.data;
  }
  sync(cx) {
    if(!shown()){if(this.visible){this.visible=false;this.epoch++;this.loading=false;}return;}
    const justOpened=!this.visible;this.visible=true;
    const current=this.fixed ? this.target : source() || this.target;
    if(!current)return;
    const key=JSON.stringify([current.cwd,current.on]);
    if(current.pane && this.target?.cwd===current.cwd)this.target=current;
    if(key!==this.context || justOpened){
      this.context=key;const serial=++this.contextSerial;
      cx.timer.after(100,cx=>{if(serial===this.contextSerial && shown())this.activate(current,cx);});
    }
  }
  activate(target,cx) {
    this.contextSerial=(this.contextSerial || 0);this.target=target;this.context=JSON.stringify([target.cwd,target.on]);
    const token=++this.epoch;this.loading=true;this.error='';this.info=null;this.detail=null;this.diff=[];this.graph=[];this.dirty=[];this.prs=[];
    this.scope='all';this.limit=100;this.prPage=1;this.remoteIndex=0;this.base=null;this.branches=[];this.detailOnly=false;cx.notify();
    if(target.on){this.loading=false;this.error='第一版仅支持本机仓库。此终端属于远程机器 '+target.on+'，未读取本机同名目录。';return;}
    cx.spawn(async cx=>{try{
      const info=await this.call('meta',{cwd:target.cwd});if(token!==this.epoch)return;
      // 读取期间面板被关闭：清空上下文，下次打开时重新读取，避免一直停在「正在读取」。
      if(!shown()){this.context='';this.loading=false;return;}
      this.info=info;this.target={...target,cwd:info.root};
      this.known=this.known.filter(x=>x.cwd!==info.root);this.known.unshift({...this.target,name:info.name});this.known=this.known.slice(0,20);
      this.loading=false;this.watch(info.common,cx);if(info.gitdir!==info.common)this.watch(info.gitdir,cx);this.load(cx);
    }catch(e){if(token===this.epoch){this.error=e?.message||String(e);this.loading=false;cx.notify();}}});
  }
  watch(path,cx){
    if(this.watchers.has(path)||this.watchers.size>=8)return;
    this.watchers.add(path);
    cx.spawn(async cx=>{try{for(;;){await watchFolder(path);if(!shown() || !this.info || ![this.info.common,this.info.gitdir].includes(path))continue;
      if(this.watchQueued)continue;this.watchQueued=true;cx.timer.after(350,cx=>{this.watchQueued=false;if(shown()&&this.tab!=='prs')this.load(cx,true);});
    }}catch(_){this.watchers.delete(path);}});
  }
  repository(){return this.info?.remotes?.[this.remoteIndex]?.repo || '';}
  load(cx,force=false,append=false){
    if(!this.info || !shown())return;
    const token=++this.epoch,info=this.info,tab=this.tab,params={cwd:info.root,force};
    this.loading=true;this.error='';
    if(!append){this.detail=null;this.diff=[];this.detailOnly=false;}
    const key=JSON.stringify([tab,tab==='graph'?info.common:this.repository(),tab==='graph'?this.scope:this.prMode,this.query,tab==='graph'?this.limit:this.prPage,info.branch]);
    const cached=this.cache.get(key);if(cached&&!append){if(tab==='graph')this.graph=cached;else this.prs=cached;}
    cx.notify();
    cx.spawn(async cx=>{try{
      if(tab==='graph'){
        const [graph,dirty,branches]=await Promise.all([this.call('graph',{...params,limit:this.limit,scope:this.scope,query:this.query}),this.call('changes',params),this.call('branches',params)]);
        if(token!==this.epoch)return;if(!shown()){this.context='';return;}
        this.info=graph.meta;this.branches=branches.items;this.graph=graph.rows;this.more=graph.more;this.dirty=dirty.files;this.dirtyLimited=dirty.limited;this.cache.set(key,this.graph);
      }else if(tab==='branches'||tab==='tags'){
        const data=await this.call('branches',params);if(token!==this.epoch||!shown())return;this.branches=data.items;this.info={...this.info,...data.meta};this.more=false;
      }else{
        const data=await this.call('prs',{repo:this.repository(),mode:this.prMode,branch:info.branch,page:this.prPage,force});
        if(token!==this.epoch || !shown())return;
        this.prs=append?[...this.prs,...data.items]:data.items;this.more=data.more;this.cache.set(key,this.prs);
      }
      if(this.cache.size>16)this.cache.delete(this.cache.keys().next().value);
    }catch(e){if(token===this.epoch)this.error=e?.message||String(e);}
    finally{if(token===this.epoch){this.loading=false;cx.notify();}}});
  }
  moreRows(cx){if(this.loading||!this.more)return;if(this.tab==='graph'){this.limit+=100;this.load(cx,false,true);}else{this.prPage++;this.load(cx,false,true);}}
  openCommit(row,cx){
    if(!row.sha)return;const token=++this.detailToken,epoch=this.epoch,cwd=this.info.root;
    this.file='';this.detailTab='files';this.detail={kind:'commit',title:row.title,sha:row.sha,subtitle:row.author+' · '+ago(row.time,row.date)+' · '+row.sha.slice(0,7),files:[],body:'正在读取…'};this.diff=[];cx.notify();
    cx.spawn(async cx=>{try{const data=await this.call('commit',{cwd,sha:row.sha});if(token===this.detailToken&&epoch===this.epoch){this.detail={...this.detail,...data};if(data.files[0])this.openFile(data.files[0],cx);cx.notify();}}catch(e){if(token===this.detailToken&&epoch===this.epoch){this.error=e?.message||String(e);cx.notify();}}});
  }
  openPR(row,cx){
    const token=++this.detailToken,epoch=this.epoch,repo=this.repository();
    this.file='';this.detailTab='files';this.detail={kind:'pr',title:row.title,files:[],body:'正在读取…',url:row.url};this.diff=[];cx.notify();
    cx.spawn(async cx=>{try{const data=await this.call('pr',{repo,number:row.number});if(token!==this.detailToken||epoch!==this.epoch)return;
      const checks=(data.statusCheckRollup||[]).map(c=>(c.name||c.context||'检查')+': '+(c.conclusion||c.state||c.status||'等待'));
      const reviews=(data.reviews||[]).slice(-20).map(r=>(r.author?.login||'用户')+': '+r.state);
      this.detail={...data,repo,kind:'pr',files:data.files||[],subtitle:data.headRefName+' → '+data.baseRefName+' · '+(states[data.state]||data.state),body:(data.body||'无说明')+'\n\n审查：'+(data.reviewDecision||'暂无结果')+'\n'+reviews.join('\n')+'\n\n检查：\n'+(checks.join('\n')||'暂无检查')};cx.notify();
    }catch(e){if(token===this.detailToken&&epoch===this.epoch){this.error=e?.message||String(e);cx.notify();}}});
  }
  openFile(file,cx){
    const token=++this.fileToken,epoch=this.epoch,detail=this.detail,path=file.path;
    this.file=path;this.setDiff('正在读取差异…');cx.notify();
    cx.spawn(async cx=>{try{const data=detail.kind==='pr' ? await this.call('pr-diff',{repo:detail.repo,number:detail.number,path,page:file.page,head:detail.headRefOid}) : await this.call('diff',{cwd:this.info.root,sha:detail.sha||'',base:detail.base||'',path,untracked:file.status==='??'});
      if(token===this.fileToken&&epoch===this.epoch&&this.detail===detail){this.setDiff(data.text);if(data.limited)this.diff.push({text:'…差异超过 200 KB，已截断',kind:'',old:'',next:''});cx.notify();}
    }catch(e){if(token===this.fileToken&&epoch===this.epoch){this.error=e?.message||String(e);cx.notify();}}});
  }
  openDirty(cx){this.detailToken++;this.detailTab='files';this.detailOnly=false;this.file='';this.diff=[];this.detail={kind:'dirty',title:'未提交的改动',subtitle:'暂存区与工作区相对 HEAD 的合并差异',body:'暂存区与工作区的合并差异',files:this.dirty};if(this.dirty[0])this.openFile(this.dirty[0],cx);cx.notify();}
  openURL(url){if(/^https:\/\/github\.com\/[\w.-]+\/[\w.-]+(?:\/|$)/.test(url))exec('/usr/bin/open',[url]);}
  openRepo(cx){if(this.info?.root)exec('/usr/bin/open',[this.info.root]);}

  setDiff(text){
    // 去掉 diff --git / index / ---/+++ 头，只保留代码块；行首的 +/-/空格 改由底色和颜色表达。
    let lines=text.split('\n');const first=lines.findIndex(l=>l.startsWith('@@'));if(first>0)lines=lines.slice(first);
    let old=0,next=0,inHunk=false;
    this.diff=lines.map(text=>{const m=/^@@ -(\d+)(?:,\d+)? \+(\d+)/.exec(text);if(m){inHunk=true;old=+m[1];next=+m[2];return {text,kind:'@',old:'',next:''};}
      if(!inHunk||!'+- '.includes(text[0]||'x'))return {text,kind:'',old:'',next:''};
      const kind=text[0],body=text.slice(1)||' ';
      if(kind==='+')return {text:body,kind,old:'',next:next++};if(kind==='-')return {text:body,kind,old:old++,next:''};
      return {text:body,kind,old:old++,next:next++};});
    this.diffWidth=this.diff.reduce((n,r)=>Math.max(n,Math.min(12000,r.text.length*8+100)),400);
  }
  copy(text,cx){cx.write_to_clipboard(text);this.note='已复制到剪贴板';const n=this.noteToken=(this.noteToken||0)+1;cx.timer.after(1600,cx=>{if(this.noteToken===n){this.note='';cx.notify();}});cx.notify();}
  compare(base,sha,cx){
    const token=++this.detailToken,epoch=this.epoch;this.detailTab='files';this.file='';this.diff=[];
    this.detail={kind:'compare',base,sha,title:base.slice(0,7)+' → '+sha.slice(0,7),body:'正在计算差异…',files:[]};cx.notify();
    cx.spawn(async cx=>{try{const data=await this.call('compare',{cwd:this.info.root,base,sha});if(token===this.detailToken&&epoch===this.epoch){this.detail={...this.detail,...data};if(data.files[0])this.openFile(data.files[0],cx);cx.notify();}}catch(e){if(token===this.detailToken&&epoch===this.epoch){this.error=e?.message||String(e);cx.notify();}}});
  }
  selectTab(tab,cx){if(tab===this.tab)return;this.tab=tab;this.more=false;this.prPage=1;this.load(cx);cx.notify();}
  openBranch(row,cx){if(row.kind==='标签'){const tips=this.branches.filter(b=>b.kind!=='标签'&&b.sha===row.sha).map(b=>b.name);this.detailToken++;this.detailTab='about';this.file='';this.diff=[];this.detail={kind:'branch',tag:true,title:row.name,subtitle:'标签 · '+row.date+' · '+row.sha.slice(0,7),sha:row.sha,ref:row.ref,files:[],body:'指向提交 '+row.sha.slice(0,7)+'\n'+(tips.length?'同时是分支末端：'+tips.join('、'):'不在任何分支末端')+'\n创建于：'+row.date+'\n'+row.title};cx.notify();return;}
    this.detailToken++;this.detailTab='about';this.file='';this.diff=[];this.detail={kind:'branch',title:row.name,sha:row.sha,ref:row.ref,files:[],body:row.kind+' · '+(row.current?'当前工作分支':'')+'\n上游：'+(row.upstream||'未设置')+'\n'+(row.gone?'上游已删除':'领先 '+row.ahead+' / 落后 '+row.behind)+'\n最近提交：'+row.date+'\n'+row.title+'\n\n领先 / 落后基于本地远程跟踪引用，本操作不会 fetch。'};cx.notify();}
  graphRows(){
    const info=this.info,key=[this.graph,this.dirty.length,info?.head,this.query,this.scope].map(x=>Array.isArray(x)?x.length+':'+(x[0]?.sha||''):x).join('|');
    if(this.laidKey!==key||this.laidSrc!==this.graph){
      this.laidKey=key;this.laidSrc=this.graph;
      const dirty=!!info&&this.dirty.length>0&&!this.query&&(this.scope==='all'||this.scope==='HEAD');
      this.laid=layoutGraph(this.graph,info?.head,dirty,!!this.query);
    }
    return this.laid;
  }
  graphLane(row,t,width){
    const colors=[t.accent,t.ansi2,t.ansi5,t.ansi3,t.ansi6,t.ansi4],color=i=>colors[i%colors.length];
    const lane=div().w(width).h(H).flex_none().relative().overflow_hidden(),mid=H/2,x=lx(row.col);
    const seg=(x1,y1,x2,y2,c)=>{const p=PathBuilder.stroke(1.6).move_to(x1,y1);
      if(x1===x2)p.line_to(x2,y2);else p.cubic_bezier_to(x2,y2,x1,(y1+y2)/2,x2,(y1+y2)/2);
      lane.child(window.paint_path(p.build(),c).absolute().inset_0());};
    row.before.forEach((v,i)=>{if(v==null)return;if(v===row.sha)seg(lx(i),0,x,mid,color(i));else seg(lx(i),0,lx(i),H,color(i));});
    for(const k of row.targets)seg(x,mid,lx(k),H,color(k));
    const c=color(row.col);
    if(row.dirty)lane.child(div().absolute().left(x-5).top(mid-5).size(10).rounded(5).border_1().border_color(t.dim).bg(t.background));
    else if(row.head)lane.child(div().absolute().left(x-6).top(mid-6).size(12).rounded(6).border_2().border_color(c).bg(t.background));
    else lane.child(div().absolute().left(x-4.5).top(mid-4.5).size(9).rounded(5).bg(c));
    return lane;
  }
  refPills(refs,t){
    const local=new Set((this.info?.refs||[]).filter(r=>r.startsWith('refs/heads/')).map(r=>r.slice(11)));
    const raw=(refs||'').split(',').map(s=>s.trim()).filter(Boolean),names=new Set(raw.map(p=>p.replace(/^HEAD -> /,'')));
    // 隐藏 origin/HEAD，以及与本地分支同名、指向同一提交的远程分支
    const parts=raw.filter(p=>!/\/HEAD$/.test(p)&&!(p.includes('/')&&!local.has(p)&&names.has(p.split('/').slice(1).join('/')))).map(p=>p.startsWith('HEAD -> ')?{name:p.slice(8),kind:'current'}:p==='HEAD'?{name:'HEAD',kind:'head'}:p.startsWith('tag: ')?{name:p.slice(5),kind:'tag'}:{name:p,kind:local.has(p)?'local':'remote'});
    const pill=r=>{const base=h_flex().h(18).px(6).gap(3).flex_none().max_w(150).items_center().rounded(5).text_size(10.5).font_medium();
      const name=div().min_w(0).truncate().child(r.name);
      if(r.kind==='current')return base.bg(t.accent+'24').text_color(t.accent).child(svg(I.branch).size(10).text_color(t.accent)).child(name);
      if(r.kind==='local')return base.bg(t.accent+'12').text_color(t.accent).child(name);
      if(r.kind==='tag')return base.bg(t.ansi3+'22').text_color(t.foreground).child(svg(I.tag).size(10).text_color(t.ansi3)).child(name);
      if(r.kind==='head')return base.bg(t.blocked+'1f').text_color(t.blocked).child(name);
      return base.border_1().border_color(t.border).text_color(t.muted).child(name);};
    return parts.slice(0,3).map(pill).concat(parts.length>3?[div().flex_none().text_size(10.5).text_color(t.dim).child('+'+(parts.length-3))]:[]);
  }
  btn(id,label,action,t,on=false,icon){return h_flex().id(id).px(8).h(26).gap(5).flex_none().items_center().rounded(6).cursor_pointer().text_size(12)
    .when(on,e=>e.bg(t.selected)).text_color(on?t.foreground:t.muted).hover(s=>s.bg(on?t.selected:t.hover).text_color(t.foreground)).on_click(action)
    .when(!!icon,e=>e.child(svg(icon).size(13).text_color(on?t.accent:t.dim))).when(!!label,e=>e.child(label));}
  iconBtn(id,icon,tip,action,t,on=false){return h_flex().id(id).size(26).flex_none().items_center().justify_center().rounded(6).cursor_pointer().when(on,e=>e.bg(t.selected)).hover(s=>s.bg(on?t.selected:t.hover)).tooltip(tip).on_click(action)
    .child(svg(icon).size(14).text_color(on?t.accent:t.muted));}
  menuBtn(id,label,action,t,on=false){return h_flex().id(id).px(8).h(26).gap(4).flex_none().items_center().rounded(6).cursor_pointer().text_size(12).border_1().border_color(on?t.accent:t.border).bg(t.background).text_color(t.foreground).hover(s=>s.bg(t.hover)).on_click(action)
    .child(div().min_w(0).truncate().child(label)).child(svg(I.down).size(12).text_color(t.dim));}
  badge(label,t,color=t.muted){return div().px(6).h(18).flex_none().flex().items_center().rounded(5).bg(color+'1f').text_size(10.5).font_medium().text_color(color).child(label);}
  segment(items,current,pick,t){return h_flex().h(28).p(2).gap(2).rounded(7).bg(t.hover).children(items.map(([key,label,extra])=>{const on=key===current;
    return h_flex().id('tab-'+key).h_full().px(10).gap(5).items_center().rounded(5).cursor_pointer().text_size(12).when(on,e=>e.bg(t.background).shadow_xs()).text_color(on?t.foreground:t.muted).when(!on,e=>e.hover(s=>s.text_color(t.foreground))).on_click((_e,cx)=>pick(key,cx)).child(label)
      .when(extra!==undefined,e=>e.child(div().text_size(11).text_color(t.dim).child(String(extra))));}));}
  input(state,id,t,icon=I.search){return h_flex().h(28).w_full().px(8).gap(6).items_center().rounded(7).border_1().border_color(t.border).bg(t.background)
    .child(svg(icon).size(13).text_color(t.dim)).child(Input.new(state).id(id).flex_1().h_full().text_size(12));}
  header(t,info,cx){
    const current=this.branches.find(b=>b.current),closed=this.fixed&&this.target?.pane&&!panes().some(p=>p.pane===this.target.pane);
    const wide=this.width>=850;
    return v_flex().flex_none().gap(4).px(12).py(9).border_b(1).border_color(t.border)
      .child(h_flex().gap(4).items_center()
        .child(svg('mods/git-workbench/git.svg').size(16).text_color(info?t.accent:t.dim))
        .child(div().ml(4).min_w(0).truncate().font_semibold().text_size(13.5).child(info?.name||(this.target?basename(this.target.cwd):'Git 工作台')))
        .when(!!info,e=>e.child(h_flex().ml(4).px(6).h(20).gap(4).flex_none().items_center().rounded(5).border_1().border_color(t.border).text_size(11.5).text_color(t.muted)
          .child(svg(I.branch).size(11).text_color(t.dim)).child(div().max_w(160).truncate().child(info.branch))))
        .when(!!current?.upstream,e=>e.child(this.syncChip(current,t)))
        .child(div().flex_1())
        .child(this.btn('repo-toggle','仓库',(_e,cx)=>{this.repoPicker=!this.repoPicker;cx.notify();},t,this.repoPicker,I.folder))
        .child(this.iconBtn('pin',this.fixed?I.pin:I.pinOff,this.fixed?'已固定此仓库，点击改为跟随当前终端':'正在跟随当前终端，点击固定此仓库',(_e,cx)=>{this.fixed=!this.fixed;if(!this.fixed)this.context='';cx.notify();},t,this.fixed))
        .child(this.iconBtn('refresh',I.refresh,this.loading?'正在读取…':'刷新',(_e,cx)=>{if(!this.loading){if(info)this.load(cx,true);else if(this.target)this.activate(this.target,cx);}},t))
        .child(this.iconBtn('wide',wide?I.min:I.max,wide?'收窄面板':'加宽面板',()=>run('layout.resize',{id:'panel',px:wide?640:1000}),t))
        .child(this.iconBtn('close',I.x,'关闭',()=>run('layout.hide',{id:'panel'}),t)))
      .when(!!closed,e=>e.child(div().pl(24).text_size(11.5).text_color(t.blocked).child('来源终端已关闭，仍显示固定的仓库')));
  }
  syncChip(b,t){
    const chip=h_flex().id('sync').ml(2).h(20).px(6).gap(6).flex_none().items_center().rounded(5).text_size(11).tooltip(b.gone?'上游 '+b.upstream+' 已删除':'相对 '+b.upstream+'（基于本地远程引用，不自动 fetch）');
    if(b.gone)return chip.bg(t.blocked+'1a').text_color(t.blocked).child('上游已删除');
    if(!b.ahead&&!b.behind)return chip.text_color(t.dim).child(svg(I.check).size(11).text_color(t.ansi2)).child('已同步');
    return chip.bg(t.hover).when(b.ahead>0,e=>e.child(div().text_color(t.accent).child('↑'+b.ahead))).when(b.behind>0,e=>e.child(div().text_color(t.blocked).child('↓'+b.behind)));
  }
  repoChoices(t){
    const list=[...this.known];for(const p of panes()){const s=spaces().find(s=>s.tabs?.some(t=>t.id===p.tab));if(p.cwd&&!s?.machine&&!list.some(r=>r.cwd===p.cwd))list.push({cwd:p.cwd,pane:p.pane,on:null,label:'终端',name:basename(p.cwd)});}
    return v_flex().flex_none().px(12).py(10).gap(8).border_b(1).border_color(t.border).bg(t.chrome)
      .child(this.input(this.pathInput,'manual-path',t,I.folder))
      .child(v_flex().id('repos').max_h(150).overflow_y_scroll().gap(1).children(list.map((r,i)=>{const on=r.cwd===this.info?.root;
        return h_flex().id('repo-'+i).h(30).px(8).gap(8).items_center().rounded(6).cursor_pointer().when(on,e=>e.bg(t.selected)).hover(s=>s.bg(on?t.selected:t.hover)).on_click((_e,cx)=>{this.fixed=true;this.repoPicker=false;this.activate(r,cx);})
          .child(svg(I.folder).size(13).text_color(on?t.accent:t.dim)).child(div().flex_none().text_size(12).font_medium().child(r.name||basename(r.cwd)))
          .child(div().flex_1().min_w(0).truncate().text_size(11).text_color(t.dim).child(r.cwd));})))
      .when(!!this.info,e=>e.child(h_flex().gap(2)
        .child(this.btn('copy-root','复制路径',(_e,cx)=>this.copy(this.info.root,cx),t,false,I.copy))
        .child(this.btn('open-root','在 Finder 中显示',(_e,cx)=>this.openRepo(cx),t,false,I.folder))
        .when(!!this.repository(),e=>e.child(this.btn('repo-web','GitHub',()=>this.openURL('https://github.com/'+this.repository()),t,false,I.ext)))));
  }
  toolbar(t){
    const dirty=this.dirty.length;
    return v_flex().flex_none().px(12).pt(10).pb(8).gap(8)
      .child(h_flex().gap(8).items_center()
        .child(this.segment([['graph','提交'],['branches','分支'],['tags','标签'],['prs','拉取请求']],this.tab,(tab,cx)=>this.selectTab(tab,cx),t))
        .child(div().flex_1())
        .when(!!this.info&&this.tab!=='graph',e=>e.child(h_flex().id('dirty').px(8).h(26).gap(6).flex_none().items_center().rounded(6).cursor_pointer().text_size(12).when(this.detail?.kind==='dirty',e=>e.bg(t.selected)).text_color(dirty?t.foreground:t.dim).hover(s=>s.bg(t.hover))
          .on_click((_e,cx)=>{this.openDirty(cx);})
          .child(div().size(6).rounded(3).bg(dirty?t.blocked:t.border)).child(dirty?dirty+' 处未提交':'工作区干净'))))
      .when(this.tab==='graph'&&!!this.info,e=>e.child(h_flex().gap(6)
        .child(this.menuBtn('branch-filter',this.scope==='all'?'所有分支':this.scope==='HEAD'?'当前分支':this.scope.replace(/^refs\/(heads|remotes|tags)\//,''),(_e,cx)=>{this.branchPicker=!this.branchPicker;cx.notify();},t,this.branchPicker))
        .child(div().flex_1().min_w(0).child(this.input(this.search,'commit-search',t)))))
      .when(this.tab==='prs',e=>e.child(h_flex().gap(6).items_center()
        .child(h_flex().id('pr-modes').flex_1().min_w(0).overflow_x_scroll().gap(2).children([['branch','当前分支'],['all','全部'],['mine','我创建的'],['review','待我审查'],['open','打开'],['merged','已合并'],['closed','已关闭']].map(([mode,label])=>this.btn('mode-'+mode,label,(_e,cx)=>{this.prMode=mode;this.prPage=1;this.prs=[];this.load(cx);},t,this.prMode===mode))))
        .when((this.info?.remotes?.length||0)>1,e=>e.child(this.menuBtn('remote',this.repository(),(_e,cx)=>{this.remoteIndex=(this.remoteIndex+1)%this.info.remotes.length;this.prPage=1;this.prs=[];this.load(cx);},t)))))
      .when(!!this.base&&this.tab==='graph',e=>e.child(h_flex().h(30).px(8).gap(8).items_center().rounded(7).bg(t.accent+'14')
        .child(svg(I.compare).size(13).text_color(t.accent)).child(div().flex_none().text_size(12).font_medium().text_color(t.accent).child('起点 '+this.base.sha.slice(0,7)))
        .child(div().flex_1().min_w(0).truncate().text_size(11.5).text_color(t.muted).child('选择另一条提交，点击「对比至此」'))
        .child(this.btn('clear-base','清除',(_e,cx)=>{this.base=null;cx.notify();},t))));
  }
  branchMenu(t){
    const refs=this.info?.refs||[],groups=[['',['all','HEAD']],['本地分支',refs.filter(r=>r.startsWith('refs/heads/'))],['远程分支',refs.filter(r=>r.startsWith('refs/remotes/')&&!r.endsWith('/HEAD'))],['标签',refs.filter(r=>r.startsWith('refs/tags/'))]];
    const items=[];let i=0;
    for(const [title,list] of groups){if(!list.length)continue;
      if(title)items.push(div().h(22).px(8).pt(6).flex_none().text_size(10.5).font_medium().text_color(t.dim).child(title+' · '+list.length));
      for(const ref of list){const on=this.scope===ref,n=i++;
        items.push(h_flex().id('ref-'+n).h(26).px(8).gap(6).flex_none().items_center().rounded(5).cursor_pointer().text_size(12).hover(s=>s.bg(t.hover)).on_click((_e,cx)=>{this.scope=ref;this.branchPicker=false;this.limit=100;this.load(cx);})
          .child(div().w(14).flex_none().when(on,e=>e.child(svg(I.check).size(12).text_color(t.accent))))
          .when(!!title,e=>e.child(svg(title==='标签'?I.tag:I.branch).size(11).text_color(title==='标签'?t.ansi3:t.dim)))
          .child(div().flex_1().min_w(0).truncate().child(ref==='all'?'所有分支':ref==='HEAD'?'当前分支':ref.replace(/^refs\/(heads|remotes|tags)\//,''))));}}
    return v_flex().id('refs').max_h(240).flex_none().mx(12).mb(8).p(4).gap(1).rounded(8).border_1().border_color(t.border).bg(t.popover).shadow_md().overflow_y_scroll().children(items);
  }
  refTab(){return this.tab==='branches'||this.tab==='tags';}
  row(row,t){
    const item=(on,h)=>h_flex().h(h).rounded(6).cursor_pointer().when(on,e=>e.bg(t.selected)).hover(s=>s.bg(on?t.selected:t.hover));
    if(this.tab==='graph'){
      const width=Math.min(this.graphRows().max,8)*LANE+8;
      if(row.dirty)return item(this.detail?.kind==='dirty',H).items_center().pr(10).child(this.graphLane(row,t,width))
        .child(v_flex().flex_1().min_w(0).gap(2).child(div().truncate().font_medium().text_color(t.foreground).child('未提交的改动'))
          .child(div().truncate().text_size(11).text_color(t.dim).child(this.dirty.length+(this.dirtyLimited?'+':'')+' 个文件 · 点击查看差异')));
      return item(this.detail?.sha===row.sha,H).items_center().pr(10).child(this.graphLane(row,t,width))
        .child(v_flex().flex_1().min_w(0).gap(2)
          .child(h_flex().gap(6).items_center().child(div().min_w(0).truncate().text_color(t.foreground).when(row.head,e=>e.font_medium()).child(row.title||'（无提交说明）')).children(this.refPills(row.refs,t)))
          .child(h_flex().gap(6).items_center().text_size(11).text_color(t.dim)
            .child(div().min_w(0).truncate().child(row.author)).child(div().flex_none().child('·')).child(div().flex_none().child(ago(row.time,row.date)))
            .child(div().flex_none().font_family('Menlo').text_size(10.5).child(row.sha.slice(0,7)))));
    }
    if(this.tab==='tags'){
      const tips=this.branches.filter(b=>b.kind!=='标签'&&b.sha===row.sha).map(b=>b.name);
      return item(this.detail?.ref===row.ref,52).gap(10).px(8).items_center()
        .child(svg(I.tag).size(14).text_color(t.ansi3))
        .child(v_flex().flex_1().min_w(0).gap(2).child(h_flex().gap(6).items_center().child(div().min_w(0).truncate().font_medium().child(row.name))
            .children(tips.slice(0,2).map(n=>h_flex().h(18).px(6).gap(3).flex_none().max_w(140).items_center().rounded(5).border_1().border_color(t.border).text_size(10.5).text_color(t.muted).tooltip('标签打在此分支的末端提交上').child(svg(I.branch).size(10).text_color(t.dim)).child(div().min_w(0).truncate().child(n)))))
          .child(div().truncate().text_size(11).text_color(t.dim).child(row.date+' · '+row.title)))
        .child(div().font_family('Menlo').text_size(10.5).text_color(t.dim).child(row.sha.slice(0,7)));
    }
    if(this.tab==='branches')return item(this.detail?.ref===row.ref,52).gap(10).px(8).items_center()
      .child(svg(I.branch).size(14).text_color(row.current?t.ansi2:t.dim))
      .child(v_flex().flex_1().min_w(0).gap(2).child(h_flex().gap(6).items_center().child(div().min_w(0).truncate().font_medium().child(row.name))
          .when(row.current,e=>e.child(this.badge('当前',t,t.ansi2))).when(row.kind!=='本地分支',e=>e.child(this.badge(row.kind,t))))
        .child(div().truncate().text_size(11).text_color(row.gone?t.blocked:t.dim).child(row.upstream?(row.upstream+' · '+(row.gone?'上游已删除':'↑'+row.ahead+' ↓'+row.behind)):'未设置上游 · '+row.date)))
      .child(div().font_family('Menlo').text_size(10.5).text_color(t.dim).child(row.sha.slice(0,7)));
    const color=row.state==='MERGED'?t.ansi5:row.state==='CLOSED'?t.ansi1:row.state==='DRAFT'?t.muted:t.ansi2;
    return item(this.detail?.number===row.number,58).px(8).gap(10).items_center()
      .child(div().size(8).flex_none().rounded(4).bg(color))
      .child(v_flex().flex_1().min_w(0).gap(3).child(h_flex().gap(6).child(div().flex_none().text_color(t.dim).child('#'+row.number)).child(div().min_w(0).truncate().font_medium().child(row.title)))
        .child(h_flex().gap(6).items_center().child(this.badge(states[row.state]||row.state,t,color)).child(div().truncate().text_size(11).text_color(t.dim).child(row.author+' · 更新于 '+row.updated))));
  }
  emptyState(t){
    const notRepo=!this.info&&!!this.error&&!this.loading;
    const title=this.loading?'正在读取仓库…':notRepo?(this.target?.on?'暂不支持远程仓库':'这里还不是 Git 仓库'):this.info?'没有匹配的记录':'选择一个仓库';
    const detail=this.loading?'':notRepo?this.error:this.info?'调整筛选条件，或点击刷新。':'在终端中进入项目目录，或从「仓库」中选择。';
    return v_flex().absolute().inset_0().items_center().justify_center().gap(6).px(32)
      .child(svg(notRepo?I.folder:'mods/git-workbench/git.svg').size(22).text_color(t.dim))
      .child(div().mt(4).font_medium().text_color(t.foreground).child(title))
      .when(!!detail,e=>e.child(div().text_size(12).text_color(t.dim).text_center().child(detail)))
      .when(notRepo&&!!this.target?.cwd,e=>e.child(div().text_size(11).font_family('Menlo').text_color(t.dim).text_center().child(this.target.cwd)))
      .when(!this.loading&&!this.info,e=>e.child(h_flex().mt(6).child(this.btn('empty-pick','选择仓库',(_e,cx)=>{this.repoPicker=true;cx.notify();},t,true,I.folder))));
  }
  list(t){
    const rows=this.tab==='graph'?this.graphRows().rows:this.tab==='branches'?this.branches.filter(r=>r.kind!=='标签'):this.tab==='tags'?this.branches.filter(r=>r.kind==='标签'):this.prs,id='workbench-'+this.tab;
    const heights=this.tab==='graph'?H:this.refTab()?52:58;
    const count=rows.filter(r=>!r.dirty).length;
    return v_flex().flex_1().min_h(80).gap(0)
      .when(!!rows.length,e=>e.child(h_flex().h(22).px(16).items_center().text_size(11).text_color(t.dim)
        .child(div().flex_1().child(this.tab==='graph'?'提交':this.tab==='branches'?'分支与跟踪状态（基于本地引用）':this.tab==='tags'?'标签（按创建时间）':'拉取请求')).child(count+(this.more?'+':'')+' 条')))
      .child(div().flex_1().min_h(0).relative().px(8)
        .child(v_virtual_list(id,rows.length,heights,i=>this.tab==='graph'?rows[i].key:this.refTab()?rows[i].ref:String(rows[i].number),range=>{this.nearEnd=range.end>=rows.length-8;return rows.slice(range.start,range.end).map(r=>this.row(r,t));}).size_full()
          .on_item_click((key,cx)=>{if(this.tab==='graph'){if(key==='__dirty'){this.openDirty(cx);return;}const r=this.graph.find(r=>r.key===key);if(r)this.openCommit(r,cx);}else if(this.refTab()){const r=this.branches.find(r=>r.ref===key);if(r)this.openBranch(r,cx);}else{const r=this.prs.find(r=>String(r.number)===key);if(r)this.openPR(r,cx);}}))
        .child(Scrollbar.vertical(id).viewport_from_layout().absolute().inset_0())
        .on_scroll_wheel((_e,cx)=>{if(this.refTab()||this.scrollQueued)return;this.scrollQueued=true;cx.timer.after(80,cx=>{this.scrollQueued=false;if(shown()&&this.nearEnd)this.moreRows(cx);});})
        .when(!rows.length,e=>e.child(this.emptyState(t))))
      .when(this.more&&!this.refTab()&&!!rows.length,e=>e.child(h_flex().py(6).justify_center().child(this.btn('load-more',this.loading?'读取中…':'加载更多',(_e,cx)=>this.moreRows(cx),t))));
  }
  detailView(t){
    const d=this.detail,pr=d.kind==='pr',branch=d.kind==='branch';
    let box=v_flex().min_h(0).gap(0).border_t(1).border_color(t.border);
    box=this.detailOnly?box.flex_1():box.h(Math.max(240,Math.min(400,this.height*0.5)));
    return box.child(v_flex().flex_none().px(12).pt(10).pb(8).gap(6)
      .child(h_flex().gap(5).items_center().child(this.badge(pr?'PR #'+(d.number||'…'):branch?(d.tag?'标签':'分支'):d.kind==='compare'?'对比':d.kind==='dirty'?'工作区':d.sha.slice(0,7),t,t.accent))
        .child(div().flex_1().min_w(0).truncate().font_semibold().text_size(13.5).child(d.title))
        .child(this.iconBtn('detail-zoom',this.detailOnly?I.min:I.max,this.detailOnly?'返回列表':'放大详情',(_e,cx)=>{this.detailOnly=!this.detailOnly;cx.notify();},t))
        .child(this.iconBtn('detail-close',I.x,'关闭详情',(_e,cx)=>{this.detailToken++;this.fileToken++;this.detail=null;this.detailOnly=false;this.diff=[];cx.notify();},t)))
      .when(!!d.subtitle,e=>e.child(div().truncate().text_size(11).text_color(t.dim).child(d.subtitle)))
      .child(h_flex().id('detail-tools').overflow_x_scroll().gap(4).items_center()
        .child(this.segment([...(branch?[]:[['files','文件',d.files.length+(d.filesLimited?'+':'')]]),['about',pr?'说明与审查':'说明']],this.detailTab,(tab,cx)=>{this.detailTab=tab;cx.notify();},t))
        .child(div().flex_1().min_w(8))
        .when(!!d.sha,e=>e.child(this.btn('copy-sha','复制 SHA',(_e,cx)=>this.copy(d.sha,cx),t,false,I.copy)))
        .when(d.kind==='commit',e=>e.child(this.btn('set-base',this.base?.sha===d.sha?'已设为起点':'设为起点',(_e,cx)=>{this.base={sha:d.sha,title:d.title};cx.notify();},t,this.base?.sha===d.sha,I.compare)))
        .when(d.kind==='commit'&&!!this.base&&this.base.sha!==d.sha,e=>e.child(this.btn('compare-to','对比至此',(_e,cx)=>this.compare(this.base.sha,d.sha,cx),t,true,I.compare)))
        .when(branch,e=>e.child(this.btn('branch-history','查看历史',(_e,cx)=>{this.scope=d.ref;this.tab='graph';this.limit=100;this.load(cx);},t)))
        .when(branch&&!!this.info?.head,e=>e.child(this.btn('branch-compare','与 HEAD 对比',(_e,cx)=>this.compare(d.sha,this.info.head,cx),t)))
        .when(pr&&!!d.url,e=>e.child(this.btn('copy-pr','复制链接',(_e,cx)=>this.copy(d.url,cx),t,false,I.copy)))
        .when(!!d.url||!!d.sha&&!!this.repository(),e=>e.child(this.btn('detail-web','在 GitHub 打开',()=>this.openURL(d.url||'https://github.com/'+this.repository()+'/commit/'+d.sha),t,false,I.ext)))))
      .when(this.detailTab==='about',e=>e.child(div().id('detail-body').flex_1().min_h(0).px(14).py(8).overflow_y_scroll().text_size(12).line_height('19px').child(d.title+'\n\n'+(d.body||'暂无说明'))))
      .when(this.detailTab==='files',e=>e.child(h_flex().flex_1().min_h(0).items_stretch().border_t(1).border_color(t.border)
        .child(v_flex().w(this.width<680?165:210).flex_none().min_h(0).border_r(1).border_color(t.border)
          .child(div().h(26).px(10).flex().items_center().text_size(11).text_color(t.dim).child('变更文件'))
          .child(div().flex_1().min_h(0).relative().child(v_virtual_list('detail-files',d.files.length,28,i=>d.files[i].path,range=>d.files.slice(range.start,range.end).map(f=>h_flex().h(28).mx(4).px(6).gap(6).items_center().rounded(5).cursor_pointer().when(this.file===f.path,e=>e.bg(t.selected)).hover(s=>s.bg(this.file===f.path?t.selected:t.hover))
            .child(div().w(12).flex_none().font_family('Menlo').text_color(f.status==='removed'||f.status?.includes('D')?t.ansi1:f.status==='modified'||f.status?.includes('M')?t.blocked:t.ansi2).text_size(10.5).child((f.status||'M').slice(0,1)))
            .child(div().flex_1().min_w(0).truncate().text_size(11.5).child(f.path)))).size_full().on_item_click((path,cx)=>{const f=d.files.find(f=>f.path===path);if(f)this.openFile(f,cx);}))
            .child(Scrollbar.vertical('detail-files').viewport_from_layout().absolute().inset_0())))
        .child(v_flex().flex_1().min_w(0).min_h(0)
          .child(h_flex().h(26).px(10).gap(6).items_center().border_b(1).border_color(t.border).text_size(11).text_color(t.dim).child(div().flex_1().truncate().when(!!this.file,e=>e.font_family('Menlo')).text_color(this.file?t.foreground:t.dim).child(this.file||'选择文件查看差异'))
            .when(!!this.file,e=>e.child(this.iconBtn('copy-file',I.copy,'复制路径',(_e,cx)=>this.copy(this.file,cx),t))))
          .child(div().id('diff-x').flex_1().min_h(0).overflow_x_scrollbar().child(div().w(this.diffWidth||400).h_full().relative()
            .child(v_virtual_list('detail-diff',this.diff.length,19,i=>String(i),range=>this.diff.slice(range.start,range.end).map(r=>h_flex().h(19).gap(7).items_center().font_family('Menlo').text_size(11).bg(r.kind==='@'?t.raised:r.kind==='+'?t.ansi2+'18':r.kind==='-'?t.ansi1+'18':t.background)
              .child(div().w(34).flex_none().text_right().text_color(t.dim).child(String(r.old))).child(div().w(34).flex_none().text_right().text_color(t.dim).child(String(r.next)))
              .child(div().whitespace_nowrap().text_color(r.kind==='+'?t.ansi2:r.kind==='-'?t.ansi1:r.kind==='@'?t.dim:t.foreground).child(r.text)))).size_full())
            .child(Scrollbar.vertical('detail-diff').viewport_from_layout().absolute().inset_0())
            .when(!this.diff.length,e=>e.child(v_flex().absolute().inset_0().items_center().justify_center().gap(4).child(div().text_size(12).text_color(t.muted).child(d.files.length?'从左侧选择文件':'没有变更文件'))
              .child(div().text_size(11).text_color(t.dim).child(pr?'PR 补丁按需从 GitHub 读取':d.kind==='compare'?'对比两个提交的最终文件内容':'合并提交与第一父提交对比')))))))));
  }
  render(cx){
    this.sync(cx);const t=theme();
    return v_flex().id('git-workbench-root').size_full().min_h(0).bg(t.background).text_color(t.foreground).text_size(12.8)
      .on_size_change((size,cx)=>{if(Math.abs(this.width-size.width)>2||Math.abs(this.height-size.height)>2){this.width=size.width;this.height=size.height;cx.notify();}})
      .child(this.header(t,this.info,cx))
      .when(this.repoPicker,e=>e.child(this.repoChoices(t)))
      .when(!this.detailOnly,e=>e.child(this.toolbar(t)))
      .when(this.branchPicker&&this.tab==='graph'&&!this.detailOnly,e=>e.child(this.branchMenu(t)))
      .when(!!this.error&&!!this.info,e=>e.child(h_flex().mx(12).mb(6).px(10).py(6).gap(8).items_start().rounded(7).bg(t.blocked+'14').text_size(11.5).text_color(t.foreground).child(div().flex_1().child(this.error)).child(this.iconBtn('error-close',I.x,'关闭提示',(_e,cx)=>{this.error='';cx.notify();},t))))
      .when(!this.detailOnly,e=>e.child(this.list(t)))
      .when(!!this.detail,e=>e.child(this.detailView(t)))
      .child(h_flex().h(24).flex_none().px(12).gap(8).items_center().border_t(1).border_color(t.border).text_size(11).text_color(t.dim)
        .child(div().flex_1().truncate().text_color(this.note?t.ansi2:t.dim).child(this.note||this.info?.root||'本地 Git 工作台'))
        .child(this.loading?'读取中…':this.tab==='prs'?'GitHub · 按需更新':'本地引用 · 未自动 fetch'));
  }
}
