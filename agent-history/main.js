import { View, div, svg, image } from "gpui-kit";
import { v_flex, h_flex, InputState, Input } from "gpui-base";
import { exec, run, theme, props, closeOverlay } from "herdr";

export default class History extends View {
  init(_p, cx) {
    this.cx = cx;
    this.rows = []; this.filter = ""; this.loading = true; this.error = ""; this.expanded = {};
    this.input = InputState.new({ placeholder: "搜索对话或项目路径…" });
    this.input.on("change", (_e, cx) => { this.filter = this.input.value().toLowerCase(); cx.notify(); });
    this.input.focus();
    cx.spawn(async (cx) => {
      try {
        const r = await exec("/usr/bin/python3", ["-I", "HISTORY_SCRIPT"]);
        if (r.code !== 0) throw new Error(r.stderr || "读取失败");
        this.rows = JSON.parse(r.stdout);
      } catch (e) { this.error = String(e); }
      this.loading = false; cx.notify();
    });
  }
  open(r) {
    closeOverlay(props().overlay);
    run("tab.new", { folder: r.cwd, name: r.title.slice(0, 35), argv: [r.agent === "Codex" ? "codex" : "claude", "resume", r.id] });
  }
  groups() {
    const rows = this.rows.filter(r => (r.title + ' ' + r.cwd + ' ' + r.agent).toLowerCase().includes(this.filter)).slice(0, 150);
    const out = {};
    for (const r of rows) {
      const agent = r.agent;
      const folder = r.cwd || '未知文件夹';
      out[agent] ??= {};
      out[agent][folder] ??= [];
      out[agent][folder].push(r);
    }
    return out;
  }
  render() {
    const t = theme();
    const groups = this.groups();
    const agentOrder = ['Claude', 'Codex'];
    const agentLabel = { Claude: 'Claude', Codex: 'Codex' };
    const blocks = [];
    for (const agent of agentOrder) {
      const folders = groups[agent];
      if (!folders) continue;
      blocks.push(h_flex().id('agent-' + agent).items_center().gap(8).mt(6).mb(2)
        .child(image('icons/' + agent.toLowerCase() + '.svg').size(18))
        .child(div().font_semibold().text_color(t.foreground).child(agentLabel[agent]))
        .child(div().text_size(11).text_color(t.dim).child(`${Object.values(folders).reduce((n, a) => n + a.length, 0)} 条对话`)));
      for (const [folder, items] of Object.entries(folders)) {
        const key = agent + ':' + folder;
        const open = this.expanded[key] !== false;
        blocks.push(v_flex().id('folder-' + key).gap(2)
          .child(h_flex().px(8).py(7).gap(7).items_center().rounded(7).cursor_pointer().hover(s => s.bg(t.hover))
            .on_click(() => { this.expanded[key] = !open; this.cx.notify(); })
            .child(div().w(12).text_color(t.dim).child(open ? '▾' : '▸'))
            .child(svg('mods/files/folder.svg').size(14).text_color(t.muted))
            .child(div().flex_1().truncate().text_color(t.foreground).child(folder))
            .child(div().text_size(11).text_color(t.dim).child(String(items.length))))
          .when(open, e => e.children(items.map((r, i) => h_flex().id(`history-${agent}-${i}`).ml(23).px(8).py(7).gap(8).rounded(7).cursor_pointer().hover(s => s.bg(t.hover))
            .on_mouse_down('left', (event) => { if (event.click_count === 2) this.open(r); })
            .child(image('icons/' + agent.toLowerCase() + '.svg').size(14))
            .child(v_flex().min_w(0).flex_1().gap(2).child(div().text_color(t.foreground).truncate().child(r.title)).child(div().text_size(11).text_color(t.dim).truncate().child(new Date(r.time * 1000).toLocaleDateString()))))));
      }
    }
    return v_flex().w_full().min_h(0).p(18).gap(10).bg(t.popover).text_size(13)
      .on_key_down((e) => { if (e.key === 'escape') closeOverlay(props().overlay); })
      .child(h_flex().items_center().child(div().flex_1().text_size(15).font_semibold().text_color(t.foreground).child('对话历史')).child(div().text_size(11).text_color(t.dim).child('双击打开 · Esc 关闭')))
      .child(h_flex().h(36).px(10).gap(8).items_center().rounded(9).border_1().border_color(t.accent).bg(t.background)
        .child(svg('mods/workspace-chrome/search.svg').size(15).text_color(t.dim)).child(Input.new(this.input).flex_1().h_full().text_color(t.foreground)))
      .child(v_flex().h(420).min_h(0).overflow_y_scrollbar()
        .when(this.loading, e => e.child(div().p(12).text_color(t.dim).child('正在读取本地对话…')))
        .when(!!this.error, e => e.child(div().p(12).text_color(t.dim).child('读取失败：' + this.error)))
        .when(!this.loading && !this.error && !blocks.length, e => e.child(div().p(12).text_color(t.dim).child('没有找到匹配的对话')))
        .children(blocks));
  }
}
