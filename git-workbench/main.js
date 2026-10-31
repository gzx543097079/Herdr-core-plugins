import { View, div, svg, PathBuilder } from 'gpui-kit';
import { v_flex, h_flex, InputState, Input, v_virtual_list, Scrollbar } from 'gpui-base';
import { exec, run, theme, focused, panes, spaces, layout, watchFolder } from 'herdr';

const basename = p => (p || '').split('/').filter(Boolean).pop() || p;
const find = (node,id) => node?.id===id ? node : (node?.children || []).map(n=>find(n,id)).find(Boolean);
const shown = () => !find(layout(),'panel')?.hidden && find(layout(),'panel-body')?.active==='git-workbench';
const states = {OPEN:'打开',CLOSED:'已关闭',MERGED:'已合并',DRAFT:'草稿'};
function source() {
  const f=focused(), all=panes();
  if(!f?.cwd)return null;
  const pane=all.find(p=>p.pane===f.pane), space=spaces().find(s=>s.tabs?.some(t=>t.id===pane?.tab));
  const on=f.terminal?.includes('/') ? f.terminal.split('/')[0] : space?.machine || null;
  return {cwd:pane?.cwd || f.cwd, pane:f.pane, on, label:pane ? '终端 '+(all.indexOf(pane)+1)+' · '+(pane.title || basename(pane.cwd)) : '当前终端'};
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
      const info=await this.call('meta',{cwd:target.cwd});if(token!==this.epoch || !shown())return;
      this.info=info;this.target={...target,cwd:info.root};
      this.known=this.known.filter(x=>x.cwd!==info.root);this.known.unshift({...this.target,name:info.name});this.known=this.known.slice(0,20);
      this.loading=false;this.watch(info.common,cx);if(info.gitdir!==info.common)this.watch(info.gitdir,cx);this.load(cx);
    }catch(e){if(token===this.epoch){this.error=String(e);this.loading=false;cx.notify();}}});
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
        if(token!==this.epoch || !shown())return;
        this.info=graph.meta;this.branches=branches.items;this.graph=graph.rows;this.more=graph.more;this.dirty=dirty.files;this.dirtyLimited=dirty.limited;this.cache.set(key,this.graph);
      }else if(tab==='branches'){
        const data=await this.call('branches',params);if(token!==this.epoch||!shown())return;this.branches=data.items;this.info={...this.info,...data.meta};this.more=false;
      }else{
        const data=await this.call('prs',{repo:this.repository(),mode:this.prMode,branch:info.branch,page:this.prPage,force});
        if(token!==this.epoch || !shown())return;
        this.prs=append?[...this.prs,...data.items]:data.items;this.more=data.more;this.cache.set(key,this.prs);
      }
      if(this.cache.size>16)this.cache.delete(this.cache.keys().next().value);
    }catch(e){if(token===this.epoch)this.error=String(e);}
    finally{if(token===this.epoch){this.loading=false;cx.notify();}}});
  }
  moreRows(cx){if(this.loading||!this.more)return;if(this.tab==='graph'){this.limit+=100;this.load(cx,false,true);}else{this.prPage++;this.load(cx,false,true);}}
  openCommit(row,cx){
    if(!row.sha)return;const token=++this.detailToken,epoch=this.epoch,cwd=this.info.root;
    this.file='';this.detailTab='files';this.detail={kind:'commit',title:row.title,sha:row.sha,subtitle:row.author+' · '+row.date,files:[],body:'正在读取…'};this.diff=[];cx.notify();
    cx.spawn(async cx=>{try{const data=await this.call('commit',{cwd,sha:row.sha});if(token===this.detailToken&&epoch===this.epoch){this.detail={...this.detail,...data};cx.notify();}}catch(e){if(token===this.detailToken&&epoch===this.epoch){this.error=String(e);cx.notify();}}});
  }
  openPR(row,cx){
    const token=++this.detailToken,epoch=this.epoch,repo=this.repository();
    this.file='';this.detailTab='files';this.detail={kind:'pr',title:row.title,files:[],body:'正在读取…',url:row.url};this.diff=[];cx.notify();
    cx.spawn(async cx=>{try{const data=await this.call('pr',{repo,number:row.number});if(token!==this.detailToken||epoch!==this.epoch)return;
      const checks=(data.statusCheckRollup||[]).map(c=>(c.name||c.context||'检查')+': '+(c.conclusion||c.state||c.status||'等待'));
      const reviews=(data.reviews||[]).slice(-20).map(r=>(r.author?.login||'用户')+': '+r.state);
      this.detail={...data,repo,kind:'pr',files:data.files||[],subtitle:data.headRefName+' → '+data.baseRefName+' · '+(states[data.state]||data.state),body:(data.body||'无说明')+'\n\n审查：'+(data.reviewDecision||'暂无结果')+'\n'+reviews.join('\n')+'\n\n检查：\n'+(checks.join('\n')||'暂无检查')};cx.notify();
    }catch(e){if(token===this.detailToken&&epoch===this.epoch){this.error=String(e);cx.notify();}}});
  }
  openFile(file,cx){
    const token=++this.fileToken,epoch=this.epoch,detail=this.detail,path=file.path;
    this.file=path;this.setDiff('正在读取差异…');cx.notify();
    cx.spawn(async cx=>{try{const data=detail.kind==='pr' ? await this.call('pr-diff',{repo:detail.repo,number:detail.number,path,page:file.page,head:detail.headRefOid}) : await this.call('diff',{cwd:this.info.root,sha:detail.sha||'',base:detail.base||'',path,untracked:file.status==='??'});
      if(token===this.fileToken&&epoch===this.epoch&&this.detail===detail){this.setDiff(data.text);if(data.limited)this.diff.push({text:'…差异超过 200 KB，已截断',old:'',next:''});cx.notify();}
    }catch(e){if(token===this.fileToken&&epoch===this.epoch){this.error=String(e);cx.notify();}}});
  }
  openURL(url){if(/^https:\/\/github\.com\/[\w.-]+\/[\w.-]+(?:\/|$)/.test(url))exec('/usr/bin/open',[url]);}
  openRepo(cx){if(this.info?.root)exec('/usr/bin/open',[this.info.root]);}

  setDiff(text){
    let old=0,next=0,inHunk=false;
    this.diff=text.split('\n').map(text=>{const m=/^@@ -(\d+)(?:,\d+)? \+(\d+)/.exec(text);if(m){inHunk=true;old=+m[1];next=+m[2];return {text,old:'',next:''};}
      if(!inHunk)return {text,old:'',next:''};
      if(text[0]==='+')return {text,old:'',next:next++};if(text[0]==='-')return {text,old:old++,next:''};
      if(text[0]===' ')return {text,old:old++,next:next++};return {text,old:'',next:''};});
    this.diffWidth=this.diff.reduce((n,r)=>Math.max(n,Math.min(12000,r.text.length*8+100)),400);
  }
  copy(text,cx){cx.write_to_clipboard(text);this.note='已复制';cx.notify();}
  compare(base,sha,cx){
    const token=++this.detailToken,epoch=this.epoch;this.detailTab='files';this.file='';this.diff=[];
    this.detail={kind:'compare',base,sha,title:base.slice(0,7)+' → '+sha.slice(0,7),body:'正在计算差异…',files:[]};cx.notify();
    cx.spawn(async cx=>{try{const data=await this.call('compare',{cwd:this.info.root,base,sha});if(token===this.detailToken&&epoch===this.epoch){this.detail={...this.detail,...data};cx.notify();}}catch(e){if(token===this.detailToken&&epoch===this.epoch){this.error=String(e);cx.notify();}}});
  }
  selectTab(tab,cx){if(tab===this.tab)return;this.tab=tab;this.more=false;this.prPage=1;this.load(cx);cx.notify();}
  openBranch(row,cx){this.detailToken++;this.detailTab='about';this.file='';this.diff=[];this.detail={kind:'branch',title:row.name,sha:row.sha,ref:row.ref,files:[],body:row.kind+' · '+(row.current?'当前工作分支':'')+'\n上游：'+(row.upstream||'未设置')+'\n'+(row.gone?'上游已删除':'领先 '+row.ahead+' / 落后 '+row.behind)+'\n最近提交：'+row.date+'\n'+row.title+'\n\n领先 / 落后基于本地远程跟踪引用，本操作不会 fetch。'};cx.notify();}
  graphLane(row,t){
    const height=row.sha?44:14,lane=div().w(54).h(height).flex_none().relative().overflow_hidden(),colors=[t.accent,t.ansi2,t.ansi5,t.ansi3];
    for(let i=0;i<row.graph.length;i++){const c=row.graph[i],x=7+i*7,color=colors[Math.floor(i/2)%colors.length];if(!'|/\\*-'.includes(c))continue;
      const p=PathBuilder.stroke(1.5);if(c==='|')p.move_to(x,0).line_to(x,height);if(c==='/')p.move_to(x+7,0).line_to(x-7,height);if(c==='\\')p.move_to(x-7,0).line_to(x+7,height);if(c==='-')p.move_to(x-7,height/2).line_to(x+7,height/2);if(c==='*')p.move_to(x,0).line_to(x,row.parents?.length?height:height/2);
      lane.child(window.paint_path(p.build(),color).absolute().inset_0());if(c==='*')lane.child(div().absolute().left(x-3.5).top(height/2-3.5).size(7).rounded(4).bg(color));}
    return lane;
  }
  btn(id,label,action,t,on=false){return div().id(id).px(8).h(28).flex_none().flex().items_center().rounded(5).cursor_pointer().bg(on?t.selected:t.background).text_color(on?t.accent:t.muted).hover(s=>s.bg(t.hover)).on_click(action).child(label);}
  badge(label,t,color=t.accent){return div().px(5).h(18).flex_none().flex().items_center().rounded(4).bg(t.selected).text_size(10.5).text_color(color).child(label);}
  input(state,id){return Input.new(state).id(id).h(30).w_full().px(8).text_size(12).border_1().border_color(theme().border).rounded(5);}
  header(t,info,cx){
    const current=this.branches.find(b=>b.current),closed=this.fixed&&this.target?.pane&&!panes().some(p=>p.pane===this.target.pane);
    return v_flex().flex_none().gap(8).px(12).pt(10).pb(9).border_b(1).border_color(t.border)
      .child(h_flex().gap(6).items_center().child(svg('mods/git-workbench/git.svg').size(17).text_color(t.accent))
        .child(div().flex_1().min_w(0).truncate().font_semibold().child(info?.name||'Git 工作台'))
        .child(this.btn('repo-toggle','仓库 ▾',(_e,cx)=>{this.repoPicker=!this.repoPicker;cx.notify();},t))
        .child(this.btn('pin',this.fixed?'已固定':'跟随终端',(_e,cx)=>{this.fixed=!this.fixed;if(!this.fixed)this.context='';cx.notify();},t,this.fixed))
        .child(this.btn('refresh',this.loading?'读取中…':'刷新',(_e,cx)=>{if(!this.loading){if(info)this.load(cx,true);else if(this.target)this.activate(this.target,cx);}},t))
        .child(this.btn('wide',this.width>=850?'收窄':'展开',()=>run('layout.resize',{id:'panel',px:this.width>=850?640:1000}),t))
        .child(this.btn('close','×',()=>run('layout.hide',{id:'panel'}),t)))
      .child(h_flex().gap(8).items_center().child(this.badge(info?.branch||'未选择仓库',t,t.ansi2))
        .when(!!current?.upstream,e=>e.child(div().text_size(11).text_color(t.dim).child('↑ '+current.ahead+'   ↓ '+current.behind+' · '+current.upstream)))
        .child(div().flex_1().min_w(0).truncate().text_size(11).text_color(t.dim).child(closed?'来源终端已关闭 · 保留固定仓库':this.target?.label||'选中终端以识别仓库')));
  }
  repoChoices(t){
    const list=[...this.known];for(const p of panes()){const s=spaces().find(s=>s.tabs?.some(t=>t.id===p.tab));if(p.cwd&&!s?.machine&&!list.some(r=>r.cwd===p.cwd))list.push({cwd:p.cwd,pane:p.pane,on:null,label:'终端',name:basename(p.cwd)});}
    return v_flex().flex_none().px(12).py(8).gap(5).border_b(1).border_color(t.border)
      .child(this.input(this.pathInput,'manual-path'))
      .child(h_flex().gap(4).child(this.btn('copy-root','复制路径',(_e,cx)=>{if(this.info)this.copy(this.info.root,cx);},t)).child(this.btn('open-root','Finder',(_e,cx)=>this.openRepo(cx),t))
        .when(!!this.repository(),e=>e.child(this.btn('repo-web','GitHub',()=>this.openURL('https://github.com/'+this.repository()),t))))
      .child(v_flex().id('repos').max_h(120).overflow_y_scroll().children(list.map((r,i)=>this.btn('repo-'+i,(r.name||basename(r.cwd))+' · '+r.cwd,(_e,cx)=>{this.fixed=true;this.repoPicker=false;this.activate(r,cx);},t))));
  }
  toolbar(t){
    return v_flex().flex_none().px(12).py(8).gap(7)
      .child(h_flex().gap(5).items_center().children([['graph','提交历史'],['branches','分支 / 标签'],['prs','Pull Requests']].map(([tab,label])=>this.btn('tab-'+tab,label,(_e,cx)=>this.selectTab(tab,cx),t,this.tab===tab)))
        .child(div().flex_1()).child(this.btn('dirty','工作区 '+this.dirty.length,(_e,cx)=>{this.detailToken++;this.detailTab='files';this.detailOnly=false;this.file='';this.diff=[];this.detail={kind:'dirty',title:'未提交改动',body:'暂存区与工作区的合并差异',files:this.dirty};cx.notify();},t)))
      .when(this.tab==='graph',e=>e.child(h_flex().gap(6).child(this.btn('branch-filter',this.scope==='all'?'所有分支 ▾':this.scope==='HEAD'?'当前分支 ▾':basename(this.scope)+' ▾',(_e,cx)=>{this.branchPicker=!this.branchPicker;cx.notify();},t))
        .child(div().flex_1().min_w(0).child(this.input(this.search,'commit-search')))))
      .when(this.tab==='prs',e=>e.child(h_flex().id('pr-modes').overflow_x_scroll().gap(3).children([['branch','当前分支'],['all','全部'],['mine','我创建'],['review','待审查'],['open','打开'],['merged','已合并'],['closed','已关闭']].map(([mode,label])=>this.btn('mode-'+mode,label,(_e,cx)=>{this.prMode=mode;this.prPage=1;this.prs=[];this.load(cx);},t,this.prMode===mode)))))
      .when(this.tab==='prs',e=>e.child(this.btn('remote',this.repository()||'未配置 GitHub remote',(_e,cx)=>{if(this.info?.remotes.length>1){this.remoteIndex=(this.remoteIndex+1)%this.info.remotes.length;this.prPage=1;this.prs=[];this.load(cx);}},t)))
      .when(!!this.base&&this.tab==='graph',e=>e.child(h_flex().gap(5).items_center().child(this.badge('对比起点 '+this.base.sha.slice(0,7),t)).child(div().flex_1().truncate().text_size(11).text_color(t.dim).child('选择另一条提交，再点击「对比至此」'))
        .child(this.btn('clear-base','清除',(_e,cx)=>{this.base=null;cx.notify();},t))));
  }
  branchMenu(t){return v_flex().id('refs').max_h(180).flex_none().px(12).overflow_y_scroll().children(['all','HEAD',...(this.info?.refs||[])].map((ref,i)=>this.btn('ref-'+i,ref==='all'?'所有分支':ref==='HEAD'?'当前分支':ref.replace(/^refs\//,''),(_e,cx)=>{this.scope=ref;this.branchPicker=false;this.limit=100;this.load(cx);},t)));}
  row(row,t){
    if(this.tab==='graph'){
      const selected=this.detail?.sha===row.sha&&!!row.sha;
      return h_flex().h(row.sha?44:14).items_center().gap(4).bg(selected?t.selected:t.background).child(this.graphLane(row,t))
        .child(v_flex().flex_1().min_w(0).gap(3).child(div().truncate().child(row.title||''))
          .when(!!row.sha,e=>e.child(h_flex().gap(5).items_center().when(!!row.refs,x=>x.child(this.badge(row.refs.split(',')[0].trim().replace('HEAD -> ',''),t)))
            .child(div().flex_1().min_w(0).truncate().text_size(10.5).text_color(t.dim).child(row.author+' · '+row.date+' · '+row.sha.slice(0,7))))));
    }
    if(this.tab==='branches')return h_flex().h(58).gap(8).px(8).items_center().bg(this.detail?.ref===row.ref?t.selected:t.background)
      .child(div().w(16).flex_none().text_color(row.current?t.ansi2:t.dim).child(row.current?'●':'⑂'))
      .child(v_flex().flex_1().min_w(0).gap(4).child(h_flex().gap(6).child(div().min_w(0).truncate().font_medium().child(row.name)).child(this.badge(row.kind,t)))
        .child(div().truncate().text_size(11).text_color(t.dim).child(row.upstream?(row.upstream+' · '+(row.gone?'上游已删除':'↑ '+row.ahead+'  ↓ '+row.behind)):'未设置上游 · '+row.date)))
      .child(div().text_size(10.5).text_color(t.dim).child(row.sha.slice(0,7)));
    return v_flex().h(66).px(8).py(8).gap(6).bg(this.detail?.number===row.number?t.selected:t.background)
      .child(div().truncate().font_medium().child('#'+row.number+'  '+row.title))
      .child(h_flex().gap(7).items_center().child(this.badge(states[row.state]||row.state,t,row.state==='MERGED'?t.ansi5:row.state==='CLOSED'?t.ansi1:t.ansi2))
        .child(div().truncate().text_size(11).text_color(t.dim).child(row.author+' · '+row.updated)));
  }
  list(t){
    const rows=this.tab==='graph'?this.graph:this.tab==='branches'?this.branches:this.prs,id='workbench-'+this.tab;
    const heights=this.tab==='graph'?rows.map(r=>r.sha?44:14):this.tab==='branches'?58:66;
    return v_flex().flex_1().min_h(80).gap(0)
      .child(h_flex().h(24).px(12).items_center().bg(t.chrome).border_y(1).border_color(t.border).text_size(10.5).text_color(t.dim)
        .child(div().flex_1().child(this.tab==='graph'?'提交说明 / 引用':this.tab==='branches'?'分支与跟踪状态 · 基于本地引用':'PR / 审查状态')).child(String(rows.filter(r=>this.tab!=='graph'||r.sha).length)+' 条'))
      .child(div().flex_1().min_h(0).relative().px(8)
        .child(v_virtual_list(id,rows.length,heights,i=>this.tab==='graph'?rows[i].key:this.tab==='branches'?rows[i].ref:String(rows[i].number),range=>{this.nearEnd=range.end>=rows.length-8;return rows.slice(range.start,range.end).map(r=>this.row(r,t));}).size_full()
          .on_item_click((key,cx)=>{if(this.tab==='graph'){const r=this.graph.find(r=>r.key===key);if(r)this.openCommit(r,cx);}else if(this.tab==='branches'){const r=this.branches.find(r=>r.ref===key);if(r)this.openBranch(r,cx);}else{const r=this.prs.find(r=>String(r.number)===key);if(r)this.openPR(r,cx);}}))
        .child(Scrollbar.vertical(id).viewport_from_layout().absolute().inset_0())
        .on_scroll_wheel((_e,cx)=>{if(this.tab==='branches'||this.scrollQueued)return;this.scrollQueued=true;cx.timer.after(80,cx=>{this.scrollQueued=false;if(shown()&&this.nearEnd)this.moreRows(cx);});})
        .when(!rows.length,e=>e.child(v_flex().p(20).gap(8).child(div().font_medium().child(this.loading?'正在读取…':this.info?'没有匹配的记录':'选择一个仓库'))
          .child(div().text_size(12).text_color(t.dim).child(this.info?'调整筛选，或刷新重试。':'选中项目终端，或在「仓库」菜单输入本地路径。')))))
      .when(this.more&&this.tab!=='branches',e=>e.child(this.btn('load-more',this.loading?'读取中…':'加载更多',(_e,cx)=>this.moreRows(cx),t)));
  }
  detailView(t){
    const d=this.detail,pr=d.kind==='pr',branch=d.kind==='branch';
    let box=v_flex().min_h(0).gap(0).border_t(1).border_color(t.border);
    box=this.detailOnly?box.flex_1():box.h(Math.max(240,Math.min(400,this.height*0.5)));
    return box.child(v_flex().flex_none().px(12).py(8).gap(7)
      .child(h_flex().gap(5).items_center().child(this.badge(pr?'PR #'+(d.number||'…'):branch?'分支':d.kind==='compare'?'提交对比':d.kind==='dirty'?'工作区':d.sha.slice(0,7),t))
        .child(div().flex_1().min_w(0).truncate().font_semibold().child(d.title))
        .child(this.btn('detail-zoom',this.detailOnly?'返回列表':'放大',(_e,cx)=>{this.detailOnly=!this.detailOnly;cx.notify();},t))
        .child(this.btn('detail-close','×',(_e,cx)=>{this.detailToken++;this.fileToken++;this.detail=null;this.detailOnly=false;this.diff=[];cx.notify();},t)))
      .when(!!d.subtitle,e=>e.child(div().truncate().text_size(11).text_color(t.dim).child(d.subtitle)))
      .child(h_flex().id('detail-tools').overflow_x_scroll().gap(4)
        .when(!branch,e=>e.child(this.btn('detail-files','文件 '+d.files.length+(d.filesLimited?'+':''),(_e,cx)=>{this.detailTab='files';cx.notify();},t,this.detailTab==='files')))
        .child(this.btn('detail-about',pr?'说明与审查':'说明',(_e,cx)=>{this.detailTab='about';cx.notify();},t,this.detailTab==='about'))
        .when(!!d.sha,e=>e.child(this.btn('copy-sha','复制 SHA',(_e,cx)=>this.copy(d.sha,cx),t)))
        .when(d.kind==='commit',e=>e.child(this.btn('set-base','设为起点',(_e,cx)=>{this.base={sha:d.sha,title:d.title};cx.notify();},t)))
        .when(d.kind==='commit'&&!!this.base&&this.base.sha!==d.sha,e=>e.child(this.btn('compare-to','对比至此',(_e,cx)=>this.compare(this.base.sha,d.sha,cx),t,true)))
        .when(branch,e=>e.child(this.btn('branch-history','查看历史',(_e,cx)=>{this.scope=d.ref;this.tab='graph';this.limit=100;this.load(cx);},t)))
        .when(branch&&!!this.info?.head,e=>e.child(this.btn('branch-compare','与 HEAD 对比',(_e,cx)=>this.compare(d.sha,this.info.head,cx),t)))
        .when(pr&&!!d.url,e=>e.child(this.btn('copy-pr','复制链接',(_e,cx)=>this.copy(d.url,cx),t)))
        .when(!!d.url||!!d.sha&&!!this.repository(),e=>e.child(this.btn('detail-web','GitHub ↗',()=>this.openURL(d.url||'https://github.com/'+this.repository()+'/commit/'+d.sha),t)))))
      .when(this.detailTab==='about',e=>e.child(div().id('detail-body').flex_1().min_h(0).px(14).py(8).overflow_y_scroll().text_size(12).line_height('19px').child(d.title+'\n\n'+(d.body||'暂无说明'))))
      .when(this.detailTab==='files',e=>e.child(h_flex().flex_1().min_h(0).items_stretch().border_t(1).border_color(t.border)
        .child(v_flex().w(this.width<680?165:210).flex_none().min_h(0).border_r(1).border_color(t.border)
          .child(div().h(24).px(10).flex().items_center().bg(t.chrome).text_size(10.5).text_color(t.dim).child('变更文件'))
          .child(div().flex_1().min_h(0).relative().child(v_virtual_list('detail-files',d.files.length,29,i=>d.files[i].path,range=>d.files.slice(range.start,range.end).map(f=>h_flex().h(29).px(8).gap(5).items_center().bg(this.file===f.path?t.selected:t.background)
            .child(div().w(12).flex_none().text_color(f.status==='removed'?t.ansi1:t.ansi2).text_size(10).child((f.status||'M').slice(0,1)))
            .child(div().flex_1().min_w(0).truncate().text_size(11.5).child(f.path)))).size_full().on_item_click((path,cx)=>{const f=d.files.find(f=>f.path===path);if(f)this.openFile(f,cx);}))
            .child(Scrollbar.vertical('detail-files').viewport_from_layout().absolute().inset_0())))
        .child(v_flex().flex_1().min_w(0).min_h(0)
          .child(h_flex().h(24).px(8).items_center().bg(t.chrome).text_size(10.5).text_color(t.dim).child(div().flex_1().truncate().child(this.file||'选择文件查看差异'))
            .when(!!this.file,e=>e.child(this.btn('copy-file','复制路径',(_e,cx)=>this.copy(this.file,cx),t))))
          .child(div().id('diff-x').flex_1().min_h(0).overflow_x_scrollbar().child(div().w(this.diffWidth||400).h_full().relative()
            .child(v_virtual_list('detail-diff',this.diff.length,19,i=>String(i),range=>this.diff.slice(range.start,range.end).map(r=>h_flex().h(19).gap(7).items_center().font_family('Menlo').text_size(11).bg(r.text.startsWith('+')?t.ansi2+'12':r.text.startsWith('-')?t.ansi1+'12':t.background)
              .child(div().w(34).flex_none().text_color(t.dim).child(String(r.old))).child(div().w(34).flex_none().text_color(t.dim).child(String(r.next)))
              .child(div().whitespace_nowrap().text_color(r.text.startsWith('+')?t.ansi2:r.text.startsWith('-')?t.ansi1:t.muted).child(r.text)))).size_full())
            .child(Scrollbar.vertical('detail-diff').viewport_from_layout().absolute().inset_0())
            .when(!this.diff.length,e=>e.child(v_flex().p(18).gap(8).child(div().text_size(12).text_color(t.muted).child(d.files.length?'从左侧选择文件':'没有变更文件'))
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
      .when(!!this.error,e=>e.child(div().px(12).py(7).text_size(11.5).text_color(t.blocked).child(this.error)))
      .when(!this.detailOnly,e=>e.child(this.list(t)))
      .when(!!this.detail,e=>e.child(this.detailView(t)))
      .child(h_flex().h(23).flex_none().px(12).items_center().border_t(1).border_color(t.border).bg(t.chrome).text_size(10.5).text_color(t.dim)
        .child(div().flex_1().truncate().child(this.note||this.info?.root||'本地 Git 工作台'))
        .child(this.loading?'读取中…':this.tab==='prs'?'GitHub · 按需更新':'本地引用 · 未自动 fetch'));
  }
}
