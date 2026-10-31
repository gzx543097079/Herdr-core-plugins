import { View, div, image, svg } from 'gpui-kit';
import { h_flex, v_flex, v_virtual_list, Scrollbar } from 'gpui-base';
import { theme, run, exec, spaces, panes, focused, agents, settings, appHome } from 'herdr';

const COMMANDS = {
  Claude: [
    ['退出与控制', [['/exit','退出 CLI'],['/quit','同 /exit'],['/logout','退出账号'],['Ctrl+C','运行中：中断操作']]],
    ['会话', [['/help','查看帮助'],['/clear','开始新对话'],['/resume','恢复历史会话'],['/compact','压缩上下文']]],
    ['配置', [['/model','选择模型'],['/permissions','调整权限'],['/config','打开配置'],['/memory','管理项目记忆']]],
    ['检查', [['/status','查看会话状态'],['/context','查看上下文用量'],['/cost','查看使用统计'],['/mcp','管理 MCP 连接']]],
    ['工作流', [['/plan','进入计划模式'],['/diff','查看代码改动'],['/init','生成 CLAUDE.md'],['/tasks','查看后台任务']]],
    ['终端启动', [['claude','启动 Claude'],['claude --continue','继续上次会话'],['claude --resume','选择历史会话'],['claude --help','查看启动参数']]]
  ],
  Codex: [
    ['退出与控制', [['/exit','退出 CLI'],['/quit','同 /exit'],['/logout','退出账号'],['/stop','停止后台终端']]],
    ['会话', [['/new','开始新对话'],['/resume','恢复历史会话'],['/fork','分支当前会话'],['/compact','压缩上下文']]],
    ['配置', [['/model','选择模型'],['/permissions','调整权限'],['/status','查看会话配置'],['/mcp','查看 MCP 工具']]],
    ['检查', [['/diff','查看代码改动'],['/review','发起代码审查'],['/init','生成 AGENTS.md'],['/mention','引用项目文件']]],
    ['终端启动', [['codex','启动 Codex'],['codex resume','选择历史会话'],['codex resume --last','继续上次会话'],['codex --help','查看启动参数']]],
    ['工具', [['/copy','复制最近回复'],['/ps','查看后台终端'],['/skills','查看技能'],['/','打开命令菜单']]]
  ]
};
export default class CommandHints extends View {
  init() { this.agent='Claude'; this.skillsOpen=false; this.cache=new Map(); this.pending=new Set(); this.copied=''; }
  // 识别当前聚焦终端里运行的 CLI：Claude Code / Codex，其他程序返回 null。
  detect() {
    const f=focused(), pane=f?.pane ? panes().find(p=>p.pane===f.pane) : null;
    const app=pane?.app || agents().find(a=>a.focused)?.app || '', key=pane?.program?.key || '';
    const id=(app+' '+key).toLowerCase();
    return /claude/.test(id) ? 'Claude' : /codex/.test(id) ? 'Codex' : null;
  }
  project() { const f=focused(); return f?.cwd || panes().find(p=>p.pane===f?.pane)?.cwd || spaces().find(s=>s.active)?.folder || ''; }
  key() { return this.agent+'\n'+this.project(); }
  loadSkills(cx, force=false) {
    const key=this.key(), agent=this.agent, cwd=this.project();
    if (this.pending.has(key) || (!force && this.cache.has(key))) return;
    this.pending.add(key); cx.notify();
    cx.spawn(async cx => {
      try {
        const result=await exec('/usr/bin/python3',[appHome() + '/mods/command-hints/skills.py',agent,cwd]);
        if(result.code!==0)throw new Error(result.stderr || '读取失败');
        this.cache.set(key,{rows:JSON.parse(result.stdout)});
        // Retain at most 12 project/provider snapshots; refresh is explicit.
        if(this.cache.size>12)this.cache.delete(this.cache.keys().next().value);
      } catch(error) { this.cache.set(key,{rows:[],error:error?.message||String(error)}); }
      this.pending.delete(key); cx.notify();
    });
  }
  copy(command,cx) {
    if(command!=='Ctrl+C')cx.write_to_clipboard(command);
    this.copied=command;const token=this.copyToken=(this.copyToken||0)+1;
    cx.timer.after(command==='Ctrl+C'?4000:1600,cx=>{if(this.copyToken===token){this.copied='';cx.notify();}});
    cx.notify();
  }
  ghost(id,label,handler,t,icon) {
    return h_flex().id(id).px(8).h(24).gap(5).flex_none().items_center().rounded(6).cursor_pointer().text_size(12).text_color(t.muted).hover(s=>s.bg(t.hover).text_color(t.foreground)).on_click(handler)
      .when(!!icon,e=>e.child(svg(icon).size(13).text_color(t.dim))).when(!!label,e=>e.child(label));
  }
  segment(agent,t) {
    const on=agent===this.agent;
    return h_flex().id('commands-'+agent).gap(5).px(9).h_full().items_center().rounded(5).cursor_pointer().text_size(12)
      .when(on,e=>e.bg(t.background).shadow_xs()).text_color(on?t.foreground:t.muted).when(!on,e=>e.hover(s=>s.text_color(t.foreground)))
      .on_click((_e,cx)=>{this.agent=agent;this.copied='';if(this.skillsOpen)this.loadSkills(cx);cx.notify();})
      .child(image('icons/'+agent.toLowerCase()+'.svg').size(13)).child(agent)
      .when(this.detected===agent,e=>e.tooltip('当前终端正在运行 '+agent).child(div().size(5).rounded(3).bg(t.ansi2)));
  }
  command(command,description,t,mono) {
    const done=this.copied===command;
    return h_flex().id('cmd-'+command).h(24).gap(8).px(6).items_center().rounded(5).cursor_pointer().hover(s=>s.bg(t.hover)).on_click((_e,cx)=>this.copy(command,cx))
      .child(div().flex_none().font_family(mono).text_size(12).text_color(done?t.ansi2:t.foreground).child(command))
      .child(div().flex_1().min_w(0).truncate().text_size(11.5).text_color(t.dim).child(description))
      .when(done&&command!=='Ctrl+C',e=>e.child(svg('mods/command-hints/check.svg').size(12).text_color(t.ansi2)));
  }
  status(t) {
    if(this.copied==='Ctrl+C')return div().text_size(11.5).text_color(t.muted).child('快捷键需在 CLI 内手动按下：运行中会中断，空闲时清空输入');
    if(this.copied)return h_flex().gap(5).items_center().text_size(11.5).text_color(t.ansi2).child(svg('mods/command-hints/check.svg').size(12).text_color(t.ansi2)).child('已复制，粘贴到终端使用');
    return div().text_size(11.5).text_color(t.dim).child('点击命令复制，不会自动执行');
  }
  render(cx) {
    // 聚焦终端的 CLI 变化时自动切换；手动点选在下次 CLI 变化前保持有效。
    const detected=this.detect();
    if(detected!==this.detected){
      this.detected=detected;
      if(detected&&detected!==this.agent){this.agent=detected;this.copied='';if(this.skillsOpen)cx.timer.after(0,cx=>this.loadSkills(cx));}
    }
    const t=theme(), key=this.key(), data=this.cache.get(key), skills=data?.rows || [], mono=settings().font_family ?? 'JetBrains Mono';
    const muted=(text)=>div().px(6).py(2).text_size(11.5).text_color(t.dim).child(text);
    return v_flex().size_full().min_h(0).px(10).pt(6).pb(6).gap(6).bg(t.chrome).border_t(1).border_color(t.border).text_size(12.8)
      .child(h_flex().h(26).gap(10).items_center()
        .child(div().pl(4).font_semibold().text_color(t.foreground).child('命令提示'))
        .child(h_flex().h(26).p(2).gap(2).rounded(7).bg(t.hover).child(this.segment('Claude',t)).child(this.segment('Codex',t)))
        .child(div().flex_1().min_w(0).child(this.status(t)))
        .child(this.ghost('skills-toggle',this.skillsOpen?'隐藏 Skill':'显示 Skill',(_e,cx)=>{this.skillsOpen=!this.skillsOpen;if(this.skillsOpen)this.loadSkills(cx);cx.notify();},t))
        .child(h_flex().id('commands-hide').size(24).flex_none().items_center().justify_center().rounded(6).cursor_pointer().hover(s=>s.bg(t.hover)).tooltip('收起命令提示').on_click(()=>run('layout.hide',{id:'command-hints'}))
          .child(svg('mods/workspace-chrome/x.svg').size(13).text_color(t.muted))))
      .child(h_flex().flex_1().min_h(0).items_stretch().gap(12)
        .child(h_flex().id('command-columns').flex_1().min_w(0).items_stretch().gap(12).overflow_x_scroll().children(COMMANDS[this.agent].map(([group,rows])=>v_flex().flex_1().min_w(200).max_w(240).gap(1)
          .child(div().h(18).px(6).text_size(11).font_medium().text_color(t.muted).child(group))
          .children(rows.map(([command,description])=>this.command(command,description,t,mono))))))
        .when(this.skillsOpen,el=>el.child(v_flex().w(220).h_full().flex_none().min_h(0).pl(12).gap(1).border_l(1).border_color(t.border)
          .child(h_flex().h(18).px(6).items_center().gap(6)
            .child(div().flex_1().text_size(11).font_medium().text_color(t.muted).child('Skill 命令'+(skills.length?' · '+skills.length:'')))
            .child(h_flex().id('skills-refresh').size(18).items_center().justify_center().rounded(4).cursor_pointer().hover(s=>s.bg(t.hover)).tooltip('重新读取当前项目的 Skill').on_click((_e,cx)=>this.loadSkills(cx,true))
              .child(svg('mods/command-hints/refresh.svg').size(11).text_color(t.dim))))
          .when(!data,el=>el.child(muted(this.pending.has(key)?'正在读取…':'项目已切换，点击右上角刷新')))
          .when(!!data?.error,el=>el.child(muted('读取失败：'+data.error)))
          .when(!!data&&!skills.length&&!data.error,el=>el.child(muted('这个项目和用户目录下没有 Skill')))
          .child(div().flex_1().min_h(0).relative()
            .child(v_virtual_list('hint-skills-'+this.agent,skills.length,24,i=>skills[i].command,
              range=>skills.slice(range.start,range.end).map(row=>h_flex().h(24).px(6).gap(6).items_center().rounded(5).cursor_pointer().hover(s=>s.bg(t.hover))
                .child(div().flex_1().min_w(0).truncate().font_family(mono).text_size(12).text_color(this.copied===row.command?t.ansi2:t.foreground).child(row.command))
                .when(this.copied===row.command,e=>e.child(svg('mods/command-hints/check.svg').size(12).text_color(t.ansi2))))).size_full()
              .on_item_click((command,cx)=>this.copy(command,cx)))
            .child(Scrollbar.vertical('hint-skills-'+this.agent).viewport_from_layout().absolute().inset_0())))));
  }
}
