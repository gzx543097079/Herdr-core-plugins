import { View, div, image } from 'gpui-kit';
import { h_flex, v_flex, v_virtual_list, Scrollbar } from 'gpui-base';
import { theme, run, exec, spaces, panes, focused } from 'herdr';

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
  project() { const f=focused(); return f?.cwd || panes().find(p=>p.pane===f?.pane)?.cwd || spaces().find(s=>s.active)?.folder || ''; }
  key() { return this.agent+'\n'+this.project(); }
  loadSkills(cx, force=false) {
    const key=this.key(), agent=this.agent, cwd=this.project();
    if (this.pending.has(key) || (!force && this.cache.has(key))) return;
    this.pending.add(key); cx.notify();
    cx.spawn(async cx => {
      try {
        const result=await exec('/usr/bin/python3',['SKILLS_SCRIPT',agent,cwd]);
        if(result.code!==0)throw new Error(result.stderr || '读取失败');
        this.cache.set(key,{rows:JSON.parse(result.stdout)});
        // Retain at most 12 project/provider snapshots; refresh is explicit.
        if(this.cache.size>12)this.cache.delete(this.cache.keys().next().value);
      } catch(error) { this.cache.set(key,{rows:[],error:String(error)}); }
      this.pending.delete(key); cx.notify();
    });
  }
  copy(command,cx) { if(command!=='Ctrl+C')cx.write_to_clipboard(command); this.copied=command; cx.notify(); }
  button(id,label,handler,t) { return div().id(id).px(8).h(26).flex().items_center().rounded(5).cursor_pointer().text_color(t.muted).hover(s=>s.bg(t.hover)).on_click(handler).child(label); }
  render() {
    const t=theme(), key=this.key(), data=this.cache.get(key), skills=data?.rows || [];
    return v_flex().size_full().min_h(0).px(12).py(6).gap(5).bg(t.chrome).border_t(1).border_color(t.border).text_size(12.8)
      .child(h_flex().gap(8).items_center()
        .child(div().font_semibold().text_color(t.foreground).child('命令提示'))
        .children(['Claude','Codex'].map(agent=>h_flex().id('commands-'+agent).gap(5).px(8).h(26).items_center().rounded(5).cursor_pointer().bg(agent===this.agent?t.selected:t.chrome).text_color(t.foreground).hover(s=>s.bg(t.hover))
          .on_click((_e,cx)=>{this.agent=agent;this.copied='';if(this.skillsOpen)this.loadSkills(cx);cx.notify();})
          .child(image('icons/'+agent.toLowerCase()+'.svg').size(14)).child(agent)))
        .child(div().flex_1())
        .child(div().text_size(11).text_color(t.dim).child(this.copied==='Ctrl+C'?'在 CLI 内按 Ctrl+C；空闲时会清空输入或退出':this.copied?'已复制 '+this.copied:'命令点击复制 · 快捷键手动按下'))
        .child(this.button('skills-toggle',this.skillsOpen?'收起 Skill':'展开 Skill',(_e,cx)=>{this.skillsOpen=!this.skillsOpen;if(this.skillsOpen)this.loadSkills(cx);cx.notify();},t))
        .child(this.button('commands-hide','收起',()=>run('layout.hide',{id:'command-hints'}),t)))
      .child(h_flex().flex_1().min_h(0).items_stretch().gap(10)
        .child(h_flex().id('command-columns').flex_1().min_w(0).items_stretch().gap(8).overflow_x_scroll().children(COMMANDS[this.agent].map(([group,rows])=>v_flex().flex_1().min_w(205).max_w(235).gap(2)
          .child(div().text_size(11).text_color(t.dim).child(group))
          .children(rows.map(([command,description])=>h_flex().id('cmd-'+command).h(25).gap(6).px(5).items_center().rounded(5).cursor_pointer().hover(s=>s.bg(t.hover)).on_click((_e,cx)=>this.copy(command,cx))
            .child(div().text_color(t.foreground).child(command)).child(div().flex_1().text_size(11).truncate().text_color(t.muted).child(description)))))))
        .when(this.skillsOpen,el=>el.child(v_flex().w(210).h_full().flex_none().min_h(0).pl(12).gap(5).border_l(1).border_color(t.border)
          .child(h_flex().items_center().child(div().flex_1().text_color(t.foreground).child('Skill 命令'))
            .child(this.button('skills-refresh','刷新',(_e,cx)=>this.loadSkills(cx,true),t)))
          .when(!data,el=>el.child(div().text_size(11).text_color(t.dim).child(this.pending.has(key)?'正在读取…':'项目已切换，点击刷新加载')))
          .when(!!data?.error,el=>el.child(div().text_size(11).text_color(t.dim).child(data.error)))
          .when(!!data&&!skills.length&&!data.error,el=>el.child(div().text_size(11).text_color(t.dim).child('没有找到用户或项目 Skill')))
          .child(div().flex_1().min_h(0).relative()
            .child(v_virtual_list('hint-skills-'+this.agent,skills.length,25,i=>skills[i].command,
              range=>skills.slice(range.start,range.end).map(row=>div().h(25).px(6).flex().items_center().text_color(t.foreground).truncate().child(row.command))).size_full()
              .on_item_click((command,cx)=>this.copy(command,cx)))
            .child(Scrollbar.vertical('hint-skills-'+this.agent).viewport_from_layout().absolute().inset_0())))));
  }
}
